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


class Timer(object):

    def __init__(self, name, action, retryer):
        super(Timer, self).__init__()
        self._tmr_name = name

        if isinstance(retryer, collections.Iterable):
            if isinstance(retryer, collections.Iterator):
                raise ValueError("retryer is an Iterator (must be "
                                 "just an Iterable).")

            def retry_generator():
                return iter(retryer)

        elif isinstance(retryer, collections.Callable):
            titer = retryer()
            if not isinstance(titer, collections.Iterator):
                raise ValueError("retryer callable is not a generator.")
            retry_generator = retryer
        else:
            raise ValueError("retryer is not a generator or iterable.")

        self._tmr_retryer = retry_generator
        self._tmr_currentPauseIter = None
        self._tmr_action = action
        self._tmr_startTime = None
        self._tmr_alarmTime = None
        self._lock = Lock()
        self._lock_holdingThread = None

    def __repr__(self):
        return "Timer(%r, action=%r, retryer=%r)" % (
            self._tmr_name, self._tmr_action, self._tmr_retryer)

    @property
    def name(self):
        return self._tmr_name

    @property
    def isRunning(self):
        # If the timer is running. A timer stops automatically after all the
        # pauses have been tried.
        return self._tmr_startTime is not None

    @property
    def nextPopTime(self):
        return self._tmr_alarmTime

    @OnlyWhenLocked
    def start(self):
        "Start the timer."
        log.debug("Start timer %r.", self._tmr_name)
        self._tmr_startTime = Clock()
        self._tmr_currentPauseIter = self._tmr_retryer()
        self._tmr_setNextPopTime()

    @OnlyWhenLocked
    def stop(self):
        "Stop the timer."
        self.__stop()

    @OnlyWhenLocked
    def check(self):
        "Checks the timer, and if it has expired runs the action."

        if self._tmr_alarmTime is None:
            log.debug(
                "%r instance named %r not running.", self.__class__.__name__,
                self._tmr_name)
            return None

        now = Clock()

        log.debug("Check at %r", now)

        res = None
        if now >= self._tmr_alarmTime:
            res = self._tmr_pop()
            self._tmr_setNextPopTime()

        return res

    #
    # INTERNAL METHODS FOLLOW.
    #
    def _tmr_setNextPopTime(self):
        "Sets up the next pop time."
        if not self.isRunning:
            # Not running (perhaps the number of times to retry expired).
            return

        try:
            wait_time = next(self._tmr_currentPauseIter)
        except StopIteration:
            self.__stop()
            return

        if self._tmr_alarmTime is None:
            self._tmr_alarmTime = self._tmr_startTime + wait_time
        else:
            self._tmr_alarmTime += wait_time

        log.debug("Start time %r, pop timer %r", self._tmr_startTime,
                  self._tmr_alarmTime)

    def _tmr_pop(self):
        "Pops this timer, calling the action."
        log.debug("POP, action %r", self._tmr_action)
        if self._tmr_action is not None:
            res = self._tmr_action()
        else:
            res = None
        return res

    def __stop(self):
        self._tmr_startTime = None
        self._tmr_alarmTime = None
        self._tmr_currentPauseIter = None
