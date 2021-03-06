"""fsmtimer.py

Implements a timer class for use with an fsm.

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
import collections
import logging
from six import next
from threading import Lock
from ..util import Clock, OnlyWhenLocked

log = logging.getLogger(__name__)


class TimerError(Exception):
    pass


class NotRunning(TimerError):
    pass


class Timer(object):

    def __init__(self, name, action, retryer):
        super(Timer, self).__init__()
        self._tmr_name = name

        if isinstance(retryer, collections.Iterable):
            if isinstance(retryer, collections.Iterator):
                raise TypeError("retryer is an Iterator (must be "
                                "just an Iterable).")

            def retry_generator():
                return iter(retryer)

        elif isinstance(retryer, collections.Callable):
            titer = retryer()
            if not isinstance(titer, collections.Iterator):
                raise TypeError("retryer callable is not a generator.")
            retry_generator = retryer
        else:
            raise TypeError("retryer is not a generator or iterable.")

        self._tmr_retryer = retry_generator
        self._tmr_currentPauseIter = None
        self._tmr_action = action
        self._tmr_startTime = None
        self._tmr_alarmTime = None
        self._lock = Lock()
        self._lock_holdingThread = None

    @property
    def name(self):
        return self._tmr_name

    @property
    def was_started(self):
        # If the timer is running. A timer stops automatically after all the
        # pauses have been tried.
        return self._tmr_startTime is not None

    @property
    def has_expired(self):
        # See comment in start.
        return self.was_started and self._tmr_alarmTime is None

    @property
    def nextPopTime(self):
        return self._tmr_alarmTime

    @OnlyWhenLocked
    def start(self):
        """Start the timer."""
        self._tmr_currentPauseIter = self._tmr_retryer()
        now = Clock()

        # Start time must be set after next pop time as otherwise there would
        # be a window where start_time was set but next_time was not, which
        # would make has_expired evaluate True. This can be shown in
        # test_window_expire_property by re-writing:
        #
        # self._tmr_startTime = now
        # sleep 0.000001
        # self._tmr_setNextPopTime(start_time=now)
        self._tmr_setNextPopTime(start_time=now)
        self._tmr_startTime = now

        log.info("Start timer %s at clock %s.", self._tmr_name, now)

    @OnlyWhenLocked
    def stop(self):
        """Stop the timer."""
        log.info('Stop timer %s', self._tmr_name)
        self.__stop()

    def check(self, exception_if_not_running=True):
        """Check the timer, and if it has expired runs the action.

        :returns:
            `None`, as there's no easy way of telling whether it popped or not.
        """
        if self.__should_pop_and_set_next_timer(exception_if_not_running):
            # The actual timer pop is done without the lock as it may recurse
            # to hit this fsm, which may cause this timer to be stopped, which
            # needs the lock.
            self._tmr_pop()

    #
    # --------------------- MAGIC METHODS -------------------------------------
    #
    def __repr__(self):
        return "%s(name=%r, action=%r, retryer=%r)" % (
            type(self).__name__, self._tmr_name, self._tmr_action,
            self._tmr_retryer)

    def __del__(self):
        log.debug('__del__ %s', type(self).__name__)
        getattr(super(Timer, self), '__del__', lambda: None)()

    #
    # -----------------------INTERNAL METHODS----------------------------------
    #
    def _tmr_setNextPopTime(self, start_time=None):
        """Set up the next pop time."""
        start_time = (
            start_time if start_time is not None else self._tmr_startTime)
        try:
            wait_time = next(self._tmr_currentPauseIter)
        except StopIteration:
            self.__stop()
            return

        if self._tmr_alarmTime is None:
            self._tmr_alarmTime = start_time + wait_time
        else:
            self._tmr_alarmTime += wait_time

        log.debug("Start time was %r, next pop is now %r", start_time,
                  self._tmr_alarmTime)

    def _tmr_pop(self):
        """Pop this timer, calling the action."""
        log.info("Pop timer %s, action %r", self.name, self._tmr_action)
        act = getattr(self, '_tmr_action', None)
        if act is None:
            return None

        return act()

    def __stop(self):
        self._tmr_alarmTime = None
        self._tmr_currentPauseIter = None

    @OnlyWhenLocked
    def __should_pop_and_set_next_timer(self, exception_if_not_running=True):
        if not self.was_started:
            if not exception_if_not_running:
                return

            raise NotRunning(
                "%r instance named %r not yet started." % (
                    self.__class__.__name__, self._tmr_name))

        if self.has_expired:
            return False

        now = Clock()

        if now >= self._tmr_alarmTime:
            log.debug('Going to pop as %s >= %s', now, self._tmr_alarmTime)
            self._tmr_setNextPopTime()
            return True
        return False
