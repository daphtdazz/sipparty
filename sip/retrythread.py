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
python's and therefore the OS's conditionlock implementation.

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
import time
import threading
import logging

log = logging.getLogger(__name__)


class RetryThread(threading.Thread):

    Clock = time.clock

    def __init__(self, action=None, **kwargs):
        """Callers must be careful that they do not hold references to the
        thread an pass in actions that hold references to themselves, which
        leads to a retain deadlock (each hold the other so neither are ever
        freed).

        One way to get around this is to use the weakref module to ensure
        that if the owner of this thread needs to be referenced in the action,
        the action doesn't retain the owner.
        """
        super(RetryThread, self).__init__(**kwargs)
        self._rthr_action = action
        self._rthr_cancelled = False
        self._rthr_retryTimes = []
        self._rthr_newWorkCondition = threading.Condition()
        self._rthr_nextTimesLock = threading.Lock()

    def __del__(self):
        log.debug("Deleting thread.")
        self.cancel()
        self.join()

    def run(self):
        """Runs until cancelled.

        Note that because this method runs until cancelled, it holds a
        reference to self, and so self cannot be garbage collected until self
        has been cancelled. Therefore along with the note about retain
        deadlocks in `__init__` callers would do well to call `cancel` in the
        owner's `__del__` method.
        """
        while not self._rthr_cancelled:
            log.debug("Thread not cancelled, next retry times: %r",
                      self._rthr_retryTimes)

            with self._rthr_nextTimesLock:
                numrts = len(self._rthr_retryTimes)
            if numrts == 0:
                with self._rthr_newWorkCondition:
                    self._rthr_newWorkCondition.wait()
                log.debug("New work to do!")
                continue

            now = self.Clock()
            with self._rthr_nextTimesLock:
                next = self._rthr_retryTimes[0]
            if next > now:
                log.debug("Next try in %r seconds", next - now)
                with self._rthr_newWorkCondition:
                    self._rthr_newWorkCondition.wait(next - now)
                continue

            log.debug("Retrying as next %r <= now %r", next, now)
            action = self._rthr_action
            if action is not None:
                action()
            with self._rthr_nextTimesLock:
                del self._rthr_retryTimes[0]

        log.debug("Thread exiting.")

    def addRetryTime(self, ctime):
        """Add a time when we should retry the action. If the time is already
        in the list, then the new time is not re-added."""
        with self._rthr_nextTimesLock:
            ii = 0
            for ii, time in zip(
                    range(len(self._rthr_retryTimes)), self._rthr_retryTimes):
                if ctime < time:
                    break
                if ctime == time:
                    # This time is already present, no need to re-add it.
                    return
            else:
                ii = len(self._rthr_retryTimes)

            new_rts = list(self._rthr_retryTimes)
            new_rts.insert(ii, ctime)
            self._rthr_retryTimes = new_rts
            log.debug("Retry times: %r", self._rthr_retryTimes)

        with self._rthr_newWorkCondition:
            self._rthr_newWorkCondition.notify()

    def cancel(self):
        self._rthr_cancelled = True
        with self._rthr_newWorkCondition:
            self._rthr_newWorkCondition.notify()
