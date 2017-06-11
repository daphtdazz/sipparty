"""retrythread.py

Implements a thread that will call an action at a set of times in the future,
and that can have more times added at any point. So:

bgthr = RetryThread(action=myaction)
bgthr.start()
# Got a background thread, but haven't scheduled any pops yet.

bgthr.addRetryTime(5.5)
# Will do a pop in 5.5 seconds.

bgthr.addRetryTime(0.0)
# Will do a pop right away (but from the background thread, not the calling
# thread).

Timing will not be very precise, and basically depends on the latency of
python's and therefore the OS's select implementation.

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
from collections import Counter
import logging
from select import error as select_error, select
from six import PY2
from socket import (error as socket_error, socketpair)
import sys
import threading
from weakref import ref
from ..util import (Clock, OnlyWhenLocked, Singleton)

log = logging.getLogger(__name__)


class OwnerFreedException(RuntimeError):
    pass


class MainThreadDeadException(RuntimeError):
    pass


class _FDSource(object):

    def __init__(self, selectable, action):
        if not (isinstance(selectable, int) or hasattr(selectable, "fileno")):
            raise ValueError(
                "FD object %r is not selectable (is an int or implements "
                "fileno())." % selectable)

        super(_FDSource, self).__init__()
        self._fds_selectable = selectable
        self._fds_int = (
            self._fds_selectable
            if isinstance(self._fds_selectable, int) else
            self._fds_selectable.fileno())
        self._fds_action = action
        self._fds_maxExceptions = 10
        self._fds_exceptionCount = 0

    def __int__(self):
        return self._fds_int

    def newDataAvailable(self):
        log.debug("New data available for %r.", self)
        try:
            self._fds_action(self._fds_selectable)
            self._fds_exceptionCount = 0
        except Exception as exc:
            log.debug('Exception actioning new data %s', exc)
            if self._fds_exceptionCount >= self._fds_maxExceptions:
                raise

            self._fds_exceptionCount += 1
            log.warning(
                "%s exception (%d%s) processing new data for selectable %r "
                "(fd %d): %s",
                type(exc).__name__,
                self._fds_exceptionCount,
                'st' if self._fds_exceptionCount == 1 else
                'nd' if self._fds_exceptionCount == 2 else
                'rd' if self._fds_exceptionCount == 3 else
                'th',
                self._fds_selectable,
                self._fds_int, exc)

    def __repr__(self):
        return '%s(selectable=%r, action=%r)' % (
            type(self).__name__, self._fds_selectable, self._fds_action)


class RetryThread(Singleton):

    def __init__(self, name=None, thr_wait=False, no_reuse=None, **kwargs):
        """Initialize a new RetryThread.

        Callers must be careful that they do not hold references to the
        thread and pass in actions that hold references to themselves, which
        leads to a retain deadlock (each hold the other so neither are ever
        freed).

        I.e. avoid this:

        UserObject --retains--> RetryThread --retains--> Action (or method)
                ^                                           |
                |                                           |
                +---------------retains---------------------+

        One way to get around this is to use the weakref module so that either
        RetryThread is a weak reference in UserObject, or UserObject is a
        weak reference in Action.
        """
        if no_reuse is not None:
            kwargs['no_reuse'] = no_reuse
        super(RetryThread, self).__init__(**kwargs)

        if not name:
            num = getattr(type(self), '_retrythread_count', 0)
            name = '%s-%d' % (type(self).__name__, 0)
            type(self)._retrythread_count = num + 1
        self.name = name

        log.info("INIT %s instance name %s", type(self).__name__, self.name)
        self._rthr_retryTimes = []
        self._rthr_nextTimesLock = threading.Lock()
        self._rthr_next_wait = None
        self.__actions = []

        self._rthr_fdSources = {}
        self._rthr_dead_fds = set()

        self._rthr_cancelled = False
        self._rthr_thread = None
        self._rthr_cancelled_thread = None

        # Initialize support for util.OnlyWhenLocked
        self._lock = threading.RLock()
        self._lock_holdingThread = None

        # Set up the trigger mechanism.
        self._rthr_triggerRunFD, self._rthr_trigger_run_read_fd = socketpair()
        self.addInputFD(
            self._rthr_trigger_run_read_fd,
            lambda selectable: selectable.recv(1))

        self.thr_wait_cvar = threading.Condition()
        self.thr_do_wait = thr_wait

    @OnlyWhenLocked
    def addInputFD(self, fd, action):
        """Add file descriptor `fd` as a source to wait for data from, with
        `action` to be called when there is data available from `fd`.
        """
        newinput = _FDSource(fd, action)
        newfd = int(newinput)
        log.debug('Add FD %d:%s', newfd, fd)
        if newfd in self._rthr_fdSources or newfd in self._rthr_dead_fds:
            raise KeyError(
                "Duplicate FD source %r added to thread." % newinput)

        self._rthr_fdSources[newfd] = newinput
        self._rthr_maybe_create()
        self._rthr_triggerSpin()

    @OnlyWhenLocked
    def rmInputFD(self, fd):
        log.debug('Remove FD %s', fd)
        fd = int(_FDSource(fd, None))
        if fd in self._rthr_fdSources:
            del self._rthr_fdSources[fd]
        elif fd in self._rthr_dead_fds:
            self._rthr_dead_fds.discard(fd)
        else:
            raise KeyError(
                "FD %r cannot be removed as it is not on the thread." % fd)

        self._rthr_maybe_cancel()
        self._rthr_triggerSpin()

    def add_action(self, action):
        self.__actions.append(action)

    def addRetryTime(self, ctime):
        """Add a time when we should retry the action. If the time is already
        in the list, then the new time is not re-added."""
        log.debug("Add retry time %f to %r", ctime, self._rthr_retryTimes)
        with self._rthr_nextTimesLock:
            ii = 0
            for ii, time in zip(
                    range(len(self._rthr_retryTimes)), self._rthr_retryTimes):
                if ctime < time:
                    break

                if ctime == time:
                    # This time is already present, no need to re-add it.
                    log.debug("Time already in list.")
                    return
            else:
                ii = len(self._rthr_retryTimes)

            new_rts = list(self._rthr_retryTimes)
            new_rts.insert(ii, ctime)
            self._rthr_retryTimes = new_rts
            log.debug("Retry times: %r", self._rthr_retryTimes)

        self._rthr_maybe_create()
        self._rthr_triggerSpin()

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        log.info('DELETE %s instance: %s', type(self).__name__, self.name)

        self._rthr_cancelled = True
        self._rthr_triggerSpin()

        # self._rthr_trigger_run_read_fd.close()
        self._rthr_triggerRunFD.close()
        try:
            self._rthr_trigger_run_read_fd.close()
        except Exception as exc:
            log.debug(
                'Exception attempting to join thread in __del__: %s',
                exc
            )
        getattr(super(RetryThread, self), '__del__', lambda: None)()

    #
    # =================== INTERNAL METHODS ====================================
    #
    @staticmethod
    def _rthr_raise_no_self():
        raise OwnerFreedException('Owner of thread "%s" freed.' % (
            threading.current_thread().name,)
        )

    @staticmethod
    def _rthr_weak_run(weak_self):
        thr_name = threading.current_thread().name
        try:
            while RetryThread._rhr_weak_single_and_should_continue(weak_self):
                pass
        except OwnerFreedException:
            log.debug(
                'Owner of thread "%s" released without tidying thread.',
                thr_name
            )
        except Exception:
            log.exception('Exception causing thread %s to crash', thr_name)
        log.info('STOP thread "%s"', thr_name)

    @staticmethod
    def _rthr_get_fd_sources_and_next_wait(weak_self):
        self = weak_self()
        if self is None:
            RetryThread._rthr_raise_no_self()
        return dict(self._rthr_fdSources), self._rthr_next_wait

    @staticmethod
    def _rhr_weak_single_and_should_continue(weak_self):
        RetryThread._rthr_mark_thread_point(
            '01-single-and-continue-main-is-alive'
        )
        if not threading.main_thread().is_alive():
            raise MainThreadDeadException('Main thread dead')
        RetryThread._rthr_mark_thread_point(
            '02-single-and-continue-call-single'
        )
        RetryThread._rthr_weak_single(weak_self)
        self = weak_self()
        if self is None:
            RetryThread._rthr_raise_no_self()
        return not self._rthr_cancelled

    @staticmethod
    def _rthr_weak_single(weak_self):
        """Run a single pass of the retrythread, passed by weak reference.

        Return whether to retry or not.
        """
        def cvar(weak_self):
            self = weak_self()
            if self is not None and self.thr_do_wait:
                return self.thr_wait_cvar
            return None
        # the_cvar = cvar(weak_self)

        RetryThread._rthr_mark_thread_point(
            '03-single-get-fds'
        )
        rsrcs, next_wait = RetryThread._rthr_get_fd_sources_and_next_wait(
            weak_self
        )
        rsrckeys = rsrcs.keys()
        RetryThread._rthr_mark_thread_point(
            '04-single-get-current-thread-name'
        )
        thr_name = threading.current_thread().name
        self = None

        try:
            actual_wait = 2.0 if next_wait is None else next_wait
            log.debug(
                "thread %s select %r from %r wait %r.",
                thr_name, select, rsrckeys,
                actual_wait)

            RetryThread._rthr_mark_thread_point(
                '05-single-select'
            )
            threading.current_thread().extra_diags = (
                list(rsrckeys), actual_wait)
            rfds, wfds, efds = select(
                rsrckeys, [], rsrckeys, actual_wait)
        except select_error as exc:
            # One of the FDs is bad... work out which one and tidy up.
            log.warning(
                "thread %s one of %r is a bad file descriptor: %r", thr_name,
                rsrckeys, exc)
            self = weak_self()
            if self is None:
                RetryThread._rthr_raise_no_self()

            for rk in rsrckeys:
                try:
                    log.debug('Test fd %d', rk)
                    select([rk], [], [rk], 0)
                except select_error:
                    log.warning('Removing dead file descriptor %d', rk)
                    self._mark_input_fd_dead(rk)

            # Exceptions hold onto information about the stack,
            # which means holding onto some of the objects on the
            # stack. However we don't want that to happen or else
            # resource tidy-up won't happen correctly which means we
            # may never get cancelled (if the cancel is in the __del__
            # of one of the objects on the exception stack).
            #
            # Python 3 does this for us, thank you Python 3!
            if PY2:
                sys.exc_clear()
            return

        RetryThread._rthr_mark_thread_point(
            '06-single-get-self'
        )
        self = weak_self()
        if self is None:
            RetryThread._rthr_raise_no_self()

        log.debug("%s process %r, %r, %r", self, rfds, wfds, efds)
        RetryThread._rthr_mark_thread_point(
            '07-single-processfds'
        )
        if len(rfds) > 0:
            self._rthr_processSelectedReadFDs(rfds, rsrcs)

        # Check timers.
        log.debug("%s check timers", self)

        RetryThread._rthr_mark_thread_point(
            '08-single-get-next-times-lock'
        )
        with self._rthr_nextTimesLock:
            numrts = len(self._rthr_retryTimes)
            if numrts == 0:
                self._rthr_next_wait = None
                log.debug('no scheduled wake-up time')
                return

            next = self._rthr_retryTimes[0]
            now = Clock()

            if next > now:
                self._rthr_next_wait = next - now
                log.debug(
                    "%s next try in %r seconds", self, self._rthr_next_wait)
                return

            del self._rthr_retryTimes[0]

        # We have some work to do.
        log.debug("%s retrying as next %r <= now %r", self, next, now)
        for action in self.__actions:
            try:
                action()
            except Exception:
                log.exception(
                    "%s exception doing action %r:", self, action)

        # Immediately respin since we haven't checked the next timer yet.
        self._rthr_next_wait = 0
        return

    @staticmethod
    def _rthr_mark_thread_point(mp_name):
        cthr = threading.current_thread()
        cthr.rthr_mark_points = getattr(cthr, 'rthr_mark_points', Counter())
        cthr.rthr_mark_points[mp_name] += 1

    @OnlyWhenLocked
    def _mark_input_fd_dead(self, fd):
        was_still_in_sources = self._rthr_fdSources.pop(fd, None)
        if was_still_in_sources:
            self._rthr_dead_fds.add(fd)

    # The following maybes should only be called with the lock.
    def _rthr_maybe_create(self):
        if self._rthr_cancelled_thread is not None:
            log.info('JOIN thread "%s"', self._rthr_cancelled_thread.name)
            self._rthr_cancelled_thread.join()
            self._rthr_cancelled_thread = None
            self._rthr_cancelled = False

        if self._rthr_thread is None and self._rthr_outstanding_work:
            self._rthr_begin_thread()

    @property
    def _rthr_outstanding_work(self):
        return len(self._rthr_fdSources) > 1 or len(self._rthr_retryTimes) > 0

    def _rthr_maybe_cancel(self):
        if self._rthr_outstanding_work:
            # outstanding work, no need to cancel
            return

        log.info('CANCEL worker of RetryThread "%s"', self.name)
        self._rthr_cancelled = True
        self._rthr_thread = None

    def _rthr_begin_thread(self):
        self._rthr_thread = threading.Thread(
            name='worker for %s' % (self.name,),
            target=self._rthr_weak_run,
            args=(ref(self),)
        )
        log.info('START thread')
        self._rthr_thread.start()

    def _rthr_processSelectedReadFDs(self, rfds, rsrcs):
        for rfd in rfds:
            fdsrc = rsrcs[rfd]
            fdsrc.newDataAvailable()

    def _rthr_triggerSpin(self):
        log.debug("%r Trigger spin", self)
        try:
            self._rthr_triggerRunFD.send(b'1')
        except (OSError, socket_error):
            log.debug('Thread already shut down')
            pass
        log.debug('Triggered.')
