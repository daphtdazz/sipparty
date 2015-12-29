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
import logging
import select
from socket import (SHUT_RDWR, socketpair)
import sys
import threading
import time
from ..util import (Clock, OnlyWhenLocked)

log = logging.getLogger(__name__)


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
        log.debug("New data available for selectable %r.",
                  self._fds_selectable)
        try:
            self._fds_action(self._fds_selectable)
            self._fds_exceptionCount = 0
        except Exception as exc:
            if self._fds_exceptionCount >= self._fds_maxExceptions:
                raise

            self._fds_exceptionCount += 1
            log.exception(
                "Exception (%d%s) processing new data for selectable %r "
                "(fd %d):", self._fds_exceptionCount,
                'st' if self._fds_exceptionCount == 1 else
                'nd' if self._fds_exceptionCount == 2 else
                'rd' if self._fds_exceptionCount == 3 else
                'th',
                self._fds_selectable,
                self._fds_int)


class RetryThread(threading.Thread):

    def __init__(self, action=None, master_thread=None, **kwargs):
        """Callers must be careful that they do not hold references to the
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
        super(RetryThread, self).__init__(**kwargs)
        log.debug("RetryThread.__init__")
        self._rthr_action = action
        self._rthr_cancelled = False
        self._rthr_retryTimes = []
        self._rthr_nextTimesLock = threading.Lock()
        self._rthr_noWorkWait = 0.01
        self._rthr_noWorkSequence = 0

        self._rthr_fdSources = {}

        if master_thread is None:
            master_thread = threading.currentThread()
        self._rthr_masterThread = master_thread

        # Set up the trigger mechanism.
        self._rthr_triggerRunFD, output = socketpair()
        self._rthr_trigger_run_read_fd = output
        self.addInputFD(output, lambda selectable: selectable.recv(1))

        # Initialize support for util.OnlyWhenLocked
        self._lock = threading.RLock()
        self._lock_holdingThread = None

    def run(self):
        """Runs until cancelled.

        Note that because this method runs until cancelled, it holds a
        reference to self, and so self cannot be garbage collected until self
        has been cancelled. Therefore along with the note about retain
        deadlocks in `__init__` callers would do well to call `cancel` in the
        owner's `__del__` method.
        """
        wait = self._rthr_noWorkWait
        select_bad_fd_count = 0
        while self._rthr_shouldKeepRunning():

            log.debug("%s not cancelled, next retry times: %r, wait: %f. "
                      "Master thread is alive: %r.",
                      self, self._rthr_retryTimes, wait,
                      self._rthr_masterThread.isAlive())

            if self._rthr_cancelled:
                log.debug("%s cancelled.", self)
                break

            if (self._rthr_masterThread is not None and
                    not self._rthr_masterThread.isAlive()):
                log.debug("%s's master thread no longer alive.", self)
                break

            rsrcs = dict(self._rthr_fdSources)
            rsrckeys = rsrcs.keys()
            log.debug("%s wait on %r.", self, rsrckeys)
            try:
                rfds, wfds, efds = select.select(
                    rsrckeys, [], rsrckeys, wait)
                select_bad_fd_count = 0
            except select.error:
                # One of the FDs is bad... in general users should remove file
                # descriptors before shutting them down, and we can't tell
                # which has failed anyway, so we should just be able to
                # continue and find that the FD has been removed from the
                # list.
                log.debug(
                    "%s one of %r is a bad file descriptor.", self, rsrckeys)
                select_bad_fd_count += 1
                if select_bad_fd_count > 10:
                    # Doesn't seem to be clearing, stop.
                    raise

                if select_bad_fd_count == 5:
                    log.warning(
                        "%s one of %r is a bad file descriptor: error hit %r "
                        "times in a row...", self, rsrckeys,
                        select_bad_fd_count)
                continue

            log.debug("%s process %r, %r, %r", self, rfds, wfds, efds)
            self._rthr_processSelectedReadFDs(rfds, rsrcs)

            # Check timers.
            log.debug("%s check timers", self)
            with self._rthr_nextTimesLock:
                numrts = len(self._rthr_retryTimes)
                if numrts == 0:
                    # Initial no work wait is small, but do exponential
                    # backoff until the wait is over 10 seconds.
                    if wait < 10:
                        wait = (self._rthr_noWorkWait *
                                pow(2, self._rthr_noWorkSequence))
                    self._rthr_noWorkSequence += 1
                    continue

                next = self._rthr_retryTimes[0]
                now = Clock()

                if next > now:
                    wait = next - now
                    log.debug("%s next try in %r seconds", self, wait)
                    continue

                del self._rthr_retryTimes[0]

            # We have some work to do.
            log.debug("%s retrying as next %r <= now %r", self, next, now)
            action = self._rthr_action
            if action is not None:
                try:
                    action()
                except Exception as exc:
                    log.exception(
                        "%s exception doing action %r:", self, action)

                    # The exception holds onto information about the stack,
                    # which means holding onto some of the objects on the
                    # stack. However we don't want that to happen or else
                    # resource tidy-up won't happen correctly which means we
                    # may never get cancelled (if the cancel is in the __del__
                    # of one of the objects on the exception stack).
                    sys.exc_clear()

            # Immediately respin since we haven't checked the next timer yet.
            wait = 0
            self._rthr_noWorkSequence = 0

        log.debug("%s thread exiting.", self)

    @OnlyWhenLocked
    def addInputFD(self, fd, action):
        """Add file descriptor `fd` as a source to wait for data from, with
        `action` to be called when there is data available from `fd`.
        """
        newinput = _FDSource(fd, action)
        newinputint = int(newinput)
        if newinputint in self._rthr_fdSources:
            raise ValueError(
                "Duplicate FD source %r added to thread." % newinput)

        self._rthr_fdSources[newinputint] = newinput
        self._rthr_triggerSpin()

    @OnlyWhenLocked
    def rmInputFD(self, fd):
        fd = int(_FDSource(fd, None))
        if fd not in self._rthr_fdSources:
            raise ValueError(
                "FD %r cannot be removed as it is not on the thread." % fd)
        log.debug("RM FD %r", fd)
        del self._rthr_fdSources[fd]
        self._rthr_triggerSpin()

    def addRetryTime(self, ctime):
        """Add a time when we should retry the action. If the time is already
        in the list, then the new time is not re-added."""
        log.debug("Add retry time %d to %r", ctime, self._rthr_retryTimes)
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

        self._rthr_triggerSpin()

    def cancel(self):
        log.debug("Cancel retrythread")
        self._rthr_cancelled = True
        self._rthr_triggerSpin()

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        for sock in (self._rthr_trigger_run_read_fd, self._rthr_triggerRunFD):
            sock.close()

    #
    # =================== INTERNAL METHODS ====================================
    #
    def _rthr_processSelectedReadFDs(self, rfds, rsrcs):
        for rfd in rfds:
            fdsrc = rsrcs[rfd]
            fdsrc.newDataAvailable()

    def _rthr_triggerSpin(self):
        log.debug("%r Trigger spin", self)
        self._rthr_triggerRunFD.send(b'1')

    def _rthr_shouldKeepRunning(self):
        return not self._rthr_cancelled and self._rthr_masterThread.isAlive()
