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
import logging
import socket
import threading
from time import sleep
from weakref import ref
from ..fsm import (
    AsyncFSM, FSM, FSMTimeout, InitialStateKey, LockedFSM, Timer,
    TransitionKeys, UnexpectedInput)
from ..fsm import fsmtimer
from ..fsm import retrythread
from ..util import (Enum, WaitFor)
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestFSMBase(SIPPartyTestCase):
    Clock = MagicMock()

    def setUp(self):
        self.retry = 0
        self.cleanup = 0
        self.done = False

        self.Clock.return_value = 0

    def do_and_mark_completion(self, func):
        func()
        self.done = True


class TestFSM(TestFSMBase):

    def testSimple(self):
        nf = FSM(name="testfsm")
        self.assertEqual(
            str(nf),
            "'FSM' 'testfsm':\n"
            "  (No transitions.)\n"
            "Current state: 'Initial'")

        nf.addTransition("initial", "start", "starting")
        nf.addTransition("starting", "start", "starting")
        nf.addTransition("starting", "start_done", "running")
        nf.addTransition("running", "stop", "stopping")
        nf.addTransition("stopping", "stop", "stopping")
        nf.addTransition("stopping", "stop_done", "initial")
        nf.state = "initial"

        self.assertEqual(
            str(nf),
            "'FSM' 'testfsm':\n"
            "  'initial':\n"
            "    'start' -> 'starting'\n"
            "\n"
            "  'starting':\n"
            "    'start' -> 'starting'\n"
            "    'start_done' -> 'running'\n"
            "\n"
            "  'running':\n"
            "    'stop' -> 'stopping'\n"
            "\n"
            "  'stopping':\n"
            "    'stop' -> 'stopping'\n"
            "    'stop_done' -> 'initial'\n"
            "\n"
            "Current state: 'initial'"
        )

        nf.hit("start")
        self.assertEqual(nf.state, "starting")
        self.assertRaises(UnexpectedInput, lambda: nf.hit("stop"))

    def test_locked_fsm(self):

        # Create a background thread to prove that we are holding the FSM lock.
        global threadARunning
        global threadBRunning
        global counter
        global events
        threadARunning = False
        threadBRunning = False
        counter = 0
        events = []

        def runthreadA(lfsm):
            global events
            events.append('A running')
            lfsm.hit('input')

        def runthreadB(lfsm):
            global events
            global threadBRunning
            events.append('B running')
            threadBRunning = True
            lfsm.hit('input')

        def action():
            global events
            global threadBRunning
            events.append('action')
            while not threadBRunning:
                sleep(0.001)
            events.append('action ending')

        class LFSM(LockedFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    "input": {
                        TransitionKeys.NewState: "in progress",
                        TransitionKeys.Action: action
                    },
                },
                "in progress": {
                    "input": {
                        TransitionKeys.NewState: "end",
                        TransitionKeys.Action: action
                    }
                },
                'end': {}
            }

        lfsm = LFSM()
        self.assertEqual(lfsm.state, InitialStateKey)

        athread = threading.Thread(
            name='athread', target=runthreadA, args=(lfsm,))
        bthread = threading.Thread(
            name='bthread', target=runthreadB, args=(lfsm,))

        athread.start()
        WaitFor(lambda: len(events) > 1)

        bthread.start()

        athread.join()
        bthread.join()

        self.assertEqual(
            events, [
                'A running', 'action', 'B running', 'action ending', 'action',
                'action ending'])

        self.assertEqual(lfsm.state, 'end')

    @patch.object(fsmtimer, 'Clock', new=TestFSMBase.Clock)
    @patch.object(retrythread, 'Clock', new=TestFSMBase.Clock)
    def testTimer(self):
        nf = FSM(name="TestTimerFSM")

        self.assertRaises(
            TypeError,
            lambda: Timer("retry", lambda: self, 1))

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

        nf.state = "initial"
        nf.hit("start")
        self.assertEqual(self.retry, 0)
        nf.checkTimers()
        self.Clock.return_value = 4.9999
        nf.checkTimers()
        self.assertEqual(self.retry, 0)
        self.Clock.return_value = 5
        nf.checkTimers()
        self.assertEqual(self.retry, 1)
        self.Clock.return_value += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 2)
        self.Clock.return_value += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 2)

        # Timers are capable of being restarted, so we should be able to
        # restart.
        nf.hit("start")
        self.Clock.return_value += 5
        nf.checkTimers()
        self.assertEqual(self.retry, 3)

        # Transition to running and check the timer is stopped.
        nf.hit("start_done")
        self.Clock.return_value += 5
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
            self.Clock.return_value += 5
            cleanup += 1
            nf.checkTimers()
            self.assertEqual(self.cleanup, cleanup)

    def test_action_hit_exception(self):

        fsm = type('ActionHitTestFSM', (FSM,), {
            'bad_action': lambda self: self.hit('hit')})()
        fsm.addTransition('initial', 'hit', 'end', action='bad_action')
        fsm.state = 'initial'
        self.assertRaises(RuntimeError, fsm.hit, 'hit')

    def testAsyncFSM(self):
        nf = AsyncFSM(name="TestAsyncFSM")

        retry = [0]

        # Check trying to create a timer with a time that isn't iterable
        # ("1") fails.
        self.assertRaises(
            TypeError,
            lambda: Timer("retry", lambda: self, 1))

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

        nf.state = "initial"
        log.debug("Hit async FSM with start")
        nf.hit("start")
        WaitFor(lambda: nf.state == "starting", timeout_s=2)
        self.Clock.return_value = 0.1
        log.debug("clock incremented")
        WaitFor(lambda: retry[0] == 1, timeout_s=2)

    def test_async_actions(self):
        nf = AsyncFSM(name="TestAsyncActionsFSM")

        expect_args = 0
        expect_kwargs = 0
        actnow_hit = [0]

        def actnow(*args, **kwargs):
            actnow_hit[0] += 1
            self.assertEqual(len(args), expect_args)
            self.assertEqual(len(kwargs), expect_kwargs)

        nf.addTransition("stopped", "start", "running", action=actnow)
        nf.state = "stopped"
        expect_args = 3
        expect_kwargs = 2
        nf.hit("start", 1, 2, 3, a=1, b=2)
        WaitFor(lambda: actnow_hit[0] == 1)

        actnext_hit = [0]

        def actnext(arg1):
            actnext_hit[0] += 1

        nf.addTransition("running", "stop", "stopped", action=actnext)
        nf.hit("stop", 1)
        WaitFor(lambda: actnext_hit[0] == 1)

    def testFSMClass(self):
        self.subtest_FSM_class(async=False)

    def testAsyncFSMClass(self):
        self.subtest_FSM_class(async=True)

    @patch.object(fsmtimer, 'Clock', new=TestFSMBase.Clock)
    @patch.object(retrythread, 'Clock', new=TestFSMBase.Clock)
    def subtest_FSM_class(self, async):
        actnow_hit = [0]

        def actnow(*args, **kwargs):
            actnow_hit[0] += 1

        cls = AsyncFSM if async else FSM

        class FSMTestSubclass(cls):

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
                cls._fsm_state = "stopped"

            def __init__(self, *args, **kwargs):
                super(FSMTestSubclass, self).__init__(*args, **kwargs)
                self.retries = 0

            def retry_start(self):
                self.retries += 1

        log.debug(
            "FSM:%r; FSMTestSubclass:%r.", FSM._fsm_transitions,
            FSMTestSubclass._fsm_transitions)
        log.debug(
            "FSM Inputs:%r; FSMTestSubclass Inputs:%r.",
            FSM.Inputs,
            FSMTestSubclass.Inputs)
        self.assertEqual(FSM.Inputs, Enum())

        nf = FSMTestSubclass()
        nf.hit("start")
        self.assertEqual(actnow_hit[0], 1)

        def check_retries(val):
            if async:
                WaitFor(lambda: nf.retries == val, timeout_s=10)
            else:
                nf.checkTimers()
                self.assertEqual(nf.retries, val)

        self.assertEqual(nf.retries, 0)
        self.Clock.return_value = 1
        check_retries(1)
        self.Clock.return_value = 2
        check_retries(2)
        self.Clock.return_value = 3
        check_retries(3)
        nf.hit("start_done")
        self.Clock.return_value = 4
        check_retries(3)
        nf.hit("stop")
        nf.hit("start")

        # The timer endeavours not to lose pops, so if we set the clock
        # forward some number of seconds and check 3 times in a row, we
        # should pop on each one.
        self.Clock.return_value = 10
        WaitFor(lambda: nf.checkTimers() is None and nf.retries == 6)

        # The Inputs should be instance specific.
        nf.addTransition("stopped", "error", "error")
        self.assertEqual(Enum(("start", "start_done", "stop")),
                         nf.__class__.Inputs)
        self.assertEqual(Enum(("start", "start_done", "stop", "error")),
                         nf.Inputs)

        log.info("Test bad subclasses.")
        # This subclass has actions defined which are not actions. Check that
        # we handle this OK.

        class FSMTestBadSubclass(FSM):
            @classmethod
            def AddClassTransitions(cls):
                log.debug("Test bad method.")
                cls.addTimer("retry_start", "not-a-method",
                             [0])
                cls.addTransition("initial", "go", "going",
                                  start_timers=["retry_start"])
                cls._fsm_state = "initial"

        badFSM = FSMTestBadSubclass()
        badFSM.hit(badFSM.Inputs.go)
        # We get an error when we check the timer because the
        # 'not-a-method' method is not a method!
        self.assertRaises(AttributeError, badFSM.checkTimers)

    def testFDSources(self):

        nf = AsyncFSM()

        sck1, sck2 = socket.socketpair()

        datalen = [0]
        data = bytearray()

        def sck1_data_len(sck):
            data.extend(sck.recv(datalen[0]))

        nf.addFDSource(sck2, sck1_data_len)
        datalen[0] = 1
        datain = b"hello world"
        sck1.send(datain)

        WaitFor(lambda: len(data) == len(datain))

        log.debug("Remove source %d -> %d", sck2.fileno(), sck1.fileno())
        nf.rmFDSource(sck2)

    def testThreads(self):

        thr_res = [0]

        def runthread():
            thr_res[0] += 1

        class ThreadFSM(FSM):

            @classmethod
            def AddClassTransitions(cls):
                cls.addTransition(
                    "not_running", "start", "running",
                    start_threads=[runthread])
                cls.addTransition(
                    "running", "jump", "jumping",
                    start_threads=["thrmethod"])
                cls._fsm_state = "not_running"

            def thrmethod(self):
                thr_res[0] += 1

        nf = ThreadFSM()

        log.debug("Check that if we fail to add a transition the transition "
                  "configuration is not updated.")
        old_t_dict = nf._fsm_transitions
        self.assertRaises(
            ValueError,
            lambda: nf.addTransition(
                "a", "b", "c", start_threads=[(
                    "not", "all", "strings", {'this': 'is', 'a': 'map'}
                )]
            )
        )
        self.assertEqual(old_t_dict, nf._fsm_transitions)

        nf.addTransition("jumping", "stop", "not_running")

        for ii in range(8):
            nf.hit("start")
            nf.hit("jump")
            nf.hit("stop")

        WaitFor(lambda: thr_res[0] == 8 * 2)

    def testWaitFor(self):
        fsm = AsyncFSM()
        self.assertRaises(
            TypeError, fsm.waitForStateCondition, 'This is not a Callable')

    def test_async_timers(self):
        self.subTestWaitFor(async_timers=True)

    def test_sync_timers(self):
        self.subTestWaitFor(async_timers=False)

    def subTestWaitFor(self, async_timers):
        class TFSM(AsyncFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    "input": {
                        TransitionKeys.NewState: "in progress"
                    },
                    "cancel": {
                        TransitionKeys.NewState: "end"
                    }
                },
                "in progress": {
                    "input": {
                        TransitionKeys.NewState: "end"
                    }
                },
                "end": {
                    "reset": {
                        TransitionKeys.NewState:
                        InitialStateKey
                    },
                    "cancel_to_null_state": {
                        TransitionKeys.NewState: "null"
                    }
                },
                "null": {}
            }

        fsm1 = TFSM()
        fsm1.hit("input")
        fsm1.waitForStateCondition(lambda state: state == "in progress")
        self.assertEqual(fsm1.state, "in progress")
        fsm1.hit("input")
        fsm1.waitForStateCondition(lambda state: state != "in progress")
        self.assertNotEqual(fsm1.state, "in progress")
        self.assertRaises(
            FSMTimeout,
            lambda: fsm1.waitForStateCondition(
                lambda state: state == "in progress", timeout=0.1))
        self.expect_log("UnexpectedInput")
        fsm1.hit("cancel_to_null_state")
        if not async_timers:
            self.assertRaises(UnexpectedInput,
                              lambda: fsm1.hit("bad input"))

    def test_async_wait_for(self):
        class TFSM(AsyncFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    "input": {
                        TransitionKeys.NewState: "in progress"
                    },
                    "cancel": {
                        TransitionKeys.NewState: "end"
                    }
                },
                "in progress": {
                    "input": {
                        TransitionKeys.NewState: "end"
                    }
                },
                "end": {
                    "reset": {
                        TransitionKeys.NewState:
                        InitialStateKey
                    },
                    "cancel_to_null_state": {
                        TransitionKeys.NewState: "null"
                    }
                },
                "null": {}
            }

        log.info('Show that wait for works over more than one transition')
        fsm2 = TFSM()
        thr = threading.Thread(target=self.do_and_mark_completion, args=(
            lambda: fsm2.waitForStateCondition(
                lambda state: state == fsm2.States.end),))
        thr.start()
        fsm2.hit('input')
        fsm2.hit('input')
        WaitFor(lambda: self.done)
        thr.join()

    def test_lifetimes(self):

        start_calls = []

        class TFSM(AsyncFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    "input": {
                        TransitionKeys.NewState: "in progress 1",
                        TransitionKeys.Action: lambda: start_calls.append(1)
                    },
                },
                "in progress 1": {
                    "input": {
                        TransitionKeys.NewState: "in progress 2",
                    }
                },
                'in progress 2': {

                }
            }

        for level in range(2):
            del start_calls[:]
            afsm1 = TFSM()
            wptr = ref(afsm1)
            if level > 0:
                afsm1.hit('input')
                self.assertEqual(start_calls, [1])

            del afsm1
            self.assertIsNone(wptr())

    def test_multiple_actions(self):

        class TFSM(AsyncFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    "input": {
                        TransitionKeys.NewState: "end",
                        TransitionKeys.Action: ['meth1', 'meth2']
                    },
                },
                'end': {}
            }

            def __init__(self, *args, **kwargs):
                super(TFSM, self).__init__(*args, **kwargs)
                self.meth1 = MagicMock()
                self.meth2 = MagicMock()

        tfsm = TFSM()
        tfsm.hit('input')
        tfsm.meth1.assert_called_once_with()
        tfsm.meth2.assert_called_once_with()

    @patch.object(fsmtimer, 'Clock', new=TestFSMBase.Clock)
    @patch.object(retrythread, 'Clock', new=TestFSMBase.Clock)
    def test_timer_definitions(self):

        class TimerFSM(FSM):
            FSMDefinitions = {
                InitialStateKey: {
                    'input': {
                        TransitionKeys.NewState: 'running',
                        TransitionKeys.StartTimers: ['running_timer']
                    }
                },
                'running': {
                    'input': {
                        TransitionKeys.NewState: 'done',
                        TransitionKeys.StopTimers: ['running_timer']
                    }
                },
                'done': {}
            }
            FSMTimers = {
                'running_timer': ('running_timer_action', 'running_timer_gen')
            }

            timer_duration_s = 2

            def __init__(self, *args, **kwargs):
                super(TimerFSM, self).__init__(*args, **kwargs)
                self.action_count = 0

            def running_timer_gen(self):
                while True:
                    yield self.timer_duration_s

            def running_timer_action(self):
                self.action_count += 1

        tfsm = TimerFSM()
        tfsm.hit('input')
        self.assertEqual(tfsm.action_count, 0)
        self.Clock.return_value = 3
        tfsm.checkTimers()
        self.assertEqual(tfsm.action_count, 1)
        self.Clock.return_value = 3.9
        tfsm.checkTimers()
        self.assertEqual(tfsm.action_count, 1)
        self.Clock.return_value = 4
        tfsm.checkTimers()
        self.assertEqual(tfsm.action_count, 2)
        tfsm.hit('input')
        self.Clock.return_value = 6
        tfsm.checkTimers()
        self.assertEqual(tfsm.action_count, 2)

    def test_partial_actions(self):

        class TFSM(AsyncFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    "input": {
                        TransitionKeys.NewState: "end",
                        TransitionKeys.Action: [
                            ('meth1', 'arg1'), 'meth2',
                            ['meth3']]
                    },
                },
                'end': {}
            }

            def __init__(self, *args, **kwargs):
                super(TFSM, self).__init__(*args, **kwargs)
                self.meth1 = MagicMock()
                self.meth2 = MagicMock()
                self.meth3 = MagicMock()

        tfsm = TFSM()
        tfsm.hit('input')
        tfsm.meth1.assert_called_once_with('arg1')
        tfsm.meth2.assert_called_once_with()
        tfsm.meth3.assert_called_once_with()

    @patch.object(fsmtimer, 'Clock', new=TestFSMBase.Clock)
    @patch.object(retrythread, 'Clock', new=TestFSMBase.Clock)
    def test_async_timer_lifetime(self):

        class TimerFSM(AsyncFSM):
            FSMDefinitions = {
                InitialStateKey: {
                    'input': {
                        TransitionKeys.NewState: 'done',
                        TransitionKeys.StartTimers: ['running_timer']
                    }
                },
                'done': {}
            }
            FSMTimers = {
                'running_timer': ('running_timer_action', 'running_timer_gen')
            }

            timer_duration_s = 2

            def __init__(self, *args, **kwargs):
                super(TimerFSM, self).__init__(*args, **kwargs)
                self.action_count = 0

            def running_timer_gen(self):
                while True:
                    yield self.timer_duration_s

            def running_timer_action(self):
                self.action_count += 1

        tfsm = TimerFSM()
        wtfsm = ref(tfsm)
        del tfsm
        self.assertIsNone(wtfsm())


class TestFSMDelegate(TestFSMBase):

    def setUp(self):
        getattr(super(TestFSMDelegate, self), 'setUp', lambda: None)()
        self.dele_action_called = 0

    def dele_action(self, fsm):
        self.assertTrue(isinstance(fsm, FSM))
        self.dele_action_called += 1

    def test_delegate(self):
        tfsm = FSM()
        tfsm.delegate = self
        tfsm.addTransition(
            tfsm.States.Initial, 'start', 'Running', action='dele_action')
        self.assertEqual(self.dele_action_called, 0)
        tfsm.hit('start')
        self.assertEqual(self.dele_action_called, 1)
