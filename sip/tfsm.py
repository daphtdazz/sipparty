"""tfsm.py

Unit tests for the SIP FSM.

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
import sys
import time
import socket
import threading
import logging
import unittest
import pdb
import fsm
import retrythread

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class TestFSM(unittest.TestCase):

    def wait_for(self, func, timeout=2):
        assert timeout > 0.05
        now = time.clock()
        until = now + timeout
        while time.clock() < until:
            if func():
                break
            time.sleep(0.01)
        else:
            self.assertTrue(0, "Timed out waiting for %r" % func)

    def clock(self):
        return self._clock

    def setUp(self):
        self._clock = 0
        fsm.Timer.Clock = self.clock
        retrythread.RetryThread.Clock = self.clock
        self.retry = 0
        self.cleanup = 0

    def testSimple(self):
        nf = fsm.FSM(name="testfsm")
        self.assertEqual(
            str(nf),
            "'FSM' 'testfsm':\n"
            "  (No states or transitions.)\n"
            "Current state: None")

        nf.addTransition("initial", "start", "starting")
        nf.addTransition("starting", "start", "starting")
        nf.addTransition("starting", "start_done", "running")
        nf.addTransition("running", "stop", "stopping")
        nf.addTransition("stopping", "stop", "stopping")
        nf.addTransition("stopping", "stop_done", "initial")
        self.assertEqual(
            str(nf),
            "'FSM' 'testfsm':\n"
            "  'stopping':\n"
            "    'stop_done' -> 'initial'\n"
            "    'stop' -> 'stopping'\n"
            "\n"
            "  'running':\n"
            "    'stop' -> 'stopping'\n"
            "\n"
            "  'initial':\n"
            "    'start' -> 'starting'\n"
            "\n"
            "  'starting':\n"
            "    'start' -> 'starting'\n"
            "    'start_done' -> 'running'\n"
            "\n"
            "Current state: 'initial'")

        nf.hit("start")
        self.assertEqual(nf.state, "starting")
        self.assertRaises(fsm.UnexpectedInput, lambda: nf.hit("stop"))

    def testTimer(self):
        nf = fsm.FSM(name="TestTimerFSM")

        self.assertRaises(
            ValueError,
            lambda: fsm.Timer("retry", lambda: self, 1))

        def pop_func():
            self.retry += 1

        nf.addTimer("retry", pop_func,
                    [5, 5])
        nf.addTransition("initial", "start", "starting",
                         start_timers=["retry"])
        nf.addTransition("starting", "start", "starting",
                         start_timers=["retry"])
        nf.addTransition("starting", "start_done", "running",
                         stop_timers=["retry"])
        nf.addTransition("running", "stop", "initial")

        nf.setState("initial")
        nf.hit("start")
        self.assertEqual(self.retry, 0)
        nf.checkTimers()
        self._clock = 4.9999
        nf.checkTimers()
        self.assertEqual(self.retry, 0)
        self._clock = 5
        nf.checkTimers()
        self.assertEqual(self.retry, 1)
        self._clock += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 2)
        self._clock += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 2)

        # Timers are capable of being restarted, so we should be able to
        # restart.
        nf.hit("start")
        self._clock += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 3)

        # Transition to running and check the timer is stopped.
        nf.hit("start_done")
        self._clock += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 3)

        # Check generator timers work.
        def gen_timer():
            while True:
                yield 5

        def cleanup_timer():
            self.cleanup += 1

        nf.addTimer("cleanup", cleanup_timer, gen_timer)
        nf.addTransition("initial", "cleanup", "clean",
                         start_timers=["cleanup"])
        nf.hit("stop")
        nf.hit("cleanup")
        cleanup = 0
        for ii in range(20):
            self._clock += 5
            cleanup += 1
            nf.checkTimers()
            self.assertEqual(self.cleanup, cleanup)

    def testAsyncFSM(self):
        nf = fsm.FSM(name="TestAsyncFSM", asynchronous_timers=True)

        retry = [0]

        # Check trying to create a timer with a time that isn't iterable
        # ("1") fails.
        self.assertRaises(
            ValueError,
            lambda: fsm.Timer("retry", lambda: self, 1))

        def pop_func():
            log.debug("test pop_func")
            retry[0] += 1

        nf.addTimer("retry", pop_func,
                    [0.1])
        nf.addTransition("initial", "start", "starting",
                         start_timers=["retry"])
        nf.addTransition("starting", "start", "starting",
                         start_timers=["retry"])
        nf.addTransition("starting", "start_done", "running",
                         stop_timers=["retry"])
        nf.addTransition("running", "stop", "initial")

        nf.setState("initial")
        log.debug("Hit async FSM with start")
        nf.hit("start")
        self.wait_for(lambda: nf.state == "starting", timeout=2)
        self._clock = 0.1
        log.debug("clock incremented")
        self.wait_for(lambda: retry[0] == 1, timeout=2)

    def testActions(self):
        nf = fsm.FSM(name="TestActionsFSM", asynchronous_timers=True)

        expect_args = 0
        expect_kwargs = 0
        actnow_hit = [0]

        def actnow(*args, **kwargs):
            actnow_hit[0] += 1
            self.assertEqual(len(args), expect_args)
            self.assertEqual(len(kwargs), expect_kwargs)

        nf.addTransition("stopped", "start", "running", action=actnow)
        expect_args = 3
        expect_kwargs = 2
        nf.hit("start", 1, 2, 3, a=1, b=2)
        self.wait_for(lambda: actnow_hit[0] == 1)

        actnext_hit = [0]

        def actnext(arg1):
            actnext_hit[0] += 1

        nf.addTransition("running", "stop", "stopped", action=actnext)
        nf.hit("stop", 1)
        self.wait_for(lambda: actnext_hit[0] == 1)

    def testFSMClass(self):

        actnow_hit = [0]

        def actnow(*args, **kwargs):
            actnow_hit[0] += 1

        class FSMTestSubclass(fsm.FSM):

            @classmethod
            def AddClassTransitions(cls):
                log.debug("Test add class transitions.")
                cls.addTimer("retry_start", "retry_start",
                             [1, 1, 1])
                cls.addTransition("stopped", "start", "starting",
                                  start_timers=["retry_start"],
                                  action=actnow)
                cls.addTransition("starting", "start_done", "running",
                                  stop_timers=["retry_start"])
                cls.addTransition("running", "stop", "stopped")
                cls.setState("stopped")

            def __init__(self, *args, **kwargs):
                super(FSMTestSubclass, self).__init__(*args, **kwargs)
                self.retries = 0

            def retry_start(self):
                self.retries += 1

        nf = FSMTestSubclass()
        nf.hit("start")
        self.assertEqual(actnow_hit[0], 1)

        self.assertRaises(AttributeError, lambda: nf.addFDSource(1, None))

        self.assertEqual(nf.retries, 0)
        self._clock = 1
        nf.checkTimers()
        self.assertEqual(nf.retries, 1)
        nf.hit("start_done")
        self._clock = 2
        nf.checkTimers()
        self.assertEqual(nf.retries, 1)
        nf.hit("stop")
        nf.hit("start")

        # The timer endeavours not to lose pops, so if we set the clock
        # forward some number of seconds and check 3 times in a row, we
        # should pop on each one.
        self._clock = 10
        nf.checkTimers()
        self.assertEqual(nf.retries, 2)
        nf.checkTimers()
        self.assertEqual(nf.retries, 3)
        nf.checkTimers()
        self.assertEqual(nf.retries, 4)
        nf.checkTimers()
        self.assertEqual(nf.retries, 4)

        class FSMTestBadSubclass(fsm.FSM):
            @classmethod
            def AddClassTransitions(cls):
                log.debug("Test bad method.")
                cls.addTimer("retry_start", "not-a-method",
                             [1, 1, 1])
        self.assertRaises(ValueError, lambda: FSMTestBadSubclass())

    def testFDSources(self):

        nf = fsm.FSM(asynchronous_timers=True)

        sck1, sck2 = socket.socketpair()

        datalen = [0]
        data = bytearray()

        def sck1_data_len(sck):
            data.extend(sck.recv(datalen[0]))

        nf.addFDSource(sck2, sck1_data_len)
        datalen[0] = 1
        datain = b"hello world"
        sck1.send(datain)

        self.wait_for(lambda: len(data) == len(datain))

        log.debug("Remove source %d -> %d", sck2.fileno(), sck1.fileno())
        nf.rmFDSource(sck2)

    def testThreads(self):

        thr_res = [0]

        def runthread():
            thr_res[0] += 1

        class ThreadFSM(fsm.FSM):

            @classmethod
            def AddClassTransitions(cls):
                cls.addTransition(
                    "not_running", "start", "running",
                    start_threads=[("runthread", runthread)],
                    join_threads=["not-running"])
                cls.addTransition(
                    "running", "jump", "jumping",
                    start_threads=[("thrmethod", "thrmethod")])
                cls.setState("not_running")

            def thrmethod(self):
                thr_res[0] += 1

        nf = ThreadFSM()

        bgthread = threading.Thread(name="bgthread", target=runthread)

        nf.addTransition("jumping", "stop", "not_running",
                         join_threads=["thrmethod"])

        for ii in range(8):
            nf.hit("start")
            nf.hit("jump")
            nf.hit("stop")
        self.assertEqual(thr_res[0], 8 * 2)

if __name__ == "__main__":
    sys.exit(unittest.main())
