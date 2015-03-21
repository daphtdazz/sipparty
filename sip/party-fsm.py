"""party-fsm.py

Implements an `FSM` for use with sip party. This provides a generic way to
implement arbitrary state machines, with easy support for timers.

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
import time
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class TimerError(Exception):
    pass


class TimerNotRunning(TimerError):
    pass


class FSMError(Exception):
    pass


class UnexpectedInput(FSMError):
    pass


class Timer(object):

    Clock = time.clock

    def __init__(self, name, action, retryer):
        super(Timer, self).__init__()
        self._tmr_name = name

        if isinstance(retryer, collections.Iterable):
            if isinstance(retryer, collections.Iterator):
                raise ValueError("retryer is an Iterator (must be "
                                 "just an Iterable).")
            retry_generator = lambda: iter(retryer)
        elif isinstance(retryer, collections.Callable):
            titer = retryer()
            if not isinstance(titer, collections.Iterator):
                raise ValueError("retryer callable is not a generator.")
            retry_generator = retryer
        else:
            raise ValueError("retryer is not an iterator or a generator")

        self._tmr_retryer = retry_generator
        self._tmr_currentPauseIter = None
        self._tmr_action = action
        self._tmr_startTime = None
        self._tmr_alarmTime = None

    def __repr__(self):
        return "Timer(%r, action=%r, retryer=%r)" % (
            self._tmr_name, self._tmr_action, self._tmr_retryer)

    def start(self):
        log.debug("Start timer %r.", self._tmr_name)
        self._tmr_startTime = self.Clock()
        self._tmr_currentPauseIter = self._tmr_retryer()
        self._tmr_setNextPopTime()

    def stop(self):
        self._tmr_startTime = None
        self._tmr_alarmTime = None
        self._tmr_currentPauseIter = None

    def check(self):
        """Checks the timer, and if it has expired runs the action."""
        if self._tmr_alarmTime is None:
            raise TimerNotRunning(
                "%r instance named %r not running." % (
                    self.__class__.__name__, self._tmr_name))

        now = self.Clock()

        log.debug("Check at %r", now)

        res = None
        if now >= self._tmr_alarmTime:
            res = self._tmr_pop()
            self._tmr_setNextPopTime()

        return res

    def nextPop(self):
        if self._tmr_alarmTime is None:
            raise TimerNotRunning(
                "Can't get next pop as timer %r not running." % (
                    self._tmr_name))

    @property
    def isRunning(self):
        return self._tmr_startTime is not None

    def _tmr_setNextPopTime(self):
        if not self.isRunning:
            # Not running, so
            return

        try:
            wait_time = self._tmr_currentPauseIter.next()
        except StopIteration:
            self.stop()
            return

        if self._tmr_alarmTime is None:
            self._tmr_alarmTime = self._tmr_startTime + wait_time
        else:
            self._tmr_alarmTime += wait_time

        log.debug("Start time %r, pop timer %r", self._tmr_startTime,
                  self._tmr_alarmTime)

    def _tmr_pop(self):
        log.debug("POP")
        if self._tmr_action is not None:
            res = self._tmr_action()
        else:
            res = None
        return res


class FSMTimerList(object):

    def addTimer(self, timer):
        timer.start()


class FSM(object):

    KeyNewState = "new state"
    KeyAction = "action"
    KeyStartTimers = "start timers"
    KeyStopTimers = "stop timers"

    NextFSMNum = 1

    def __init__(self, name=None, asynchronous_timers=False):
        """name: a name for this FSM for debugging purposes.
        """
        super(FSM, self).__init__()

        if name is None:
            name = str(self.__class__.NextFSMNum)
            self.__class__.NextFSMNum += 1

        self._fsm_name = name
        self._fsm_transitions = {}
        self._fsm_state = None
        self._fsm_timers = {}
        self._fsm_use_async_timers = asynchronous_timers

        # Asynchronous timers are not yet implemented.
        assert not self._fsm_use_async_timers

    def addTransition(self, old_state, input, new_state, action=None,
                      start_timers=None, stop_timers=None):
        if old_state not in self._fsm_transitions:
            self._fsm_transitions[old_state] = {}

        state_trans = self._fsm_transitions[old_state]

        if input in state_trans:
            log.debug(self)
            raise ValueError(
                "FSM %r already has a transition for input %r into state "
                "%r." %
                (self._fsm_name, input, old_state))

        result = {}
        state_trans[input] = result
        result[self.KeyNewState] = new_state
        result[self.KeyAction] = action

        # Link up the timers.
        for key, timer_names in (
                (self.KeyStartTimers, start_timers),
                (self.KeyStopTimers, stop_timers)):
            timers = []
            result[key] = timers

            if timer_names is None:
                # No timers specified, so leave a blank list.
                continue

            for timer_name in timer_names:
                if timer_name not in self._fsm_timers:
                    raise ValueError("No such timer %r." % (timer_name))
                timers.append(self._fsm_timers[timer_name])

        # For convenience assume that the first transition set tells us the
        # initial state.
        if self._fsm_state is None:
            self.setState(old_state)

        log.debug("%r: %r -> %r", old_state, input, result[self.KeyNewState])

    def addTimer(self, name, *args, **kwargs):
        """Add a timer. Timers must be independent of transitions
        because they may be stopped or started at any transition."""
        newtimer = Timer(name, *args, **kwargs)
        self._fsm_timers[name] = newtimer

    def setState(self, state):
        if state not in self._fsm_transitions:
            raise ValueError(
                "FSM %r has no state %r so it cannot be set." %
                self._fsm_name, state)
        self._fsm_state = state

    def hit(self, input):
        trans = self._fsm_transitions[self._fsm_state]
        if input not in trans:
            raise UnexpectedInput(
                "Input %r to %r %r (current state %r)." %
                (input, self.__class__.__name__, self._fsm_name,
                 self._fsm_state))
        res = trans[input]
        log.debug("%r: %r -> %r", self._fsm_state, input, res)

        for st in res[self.KeyStopTimers]:
            st.stop()

        self._fsm_state = res[self.KeyNewState]

        for st in res[self.KeyStartTimers]:
            st.start()

    def checkTimers(self):
        """`checkTimers`
        """
        assert not self._fsm_use_async_timers
        for name, timer in self._fsm_timers.iteritems():
            if timer.isRunning:
                timer.check()

    @property
    def state(self):
        return self._fsm_state

    def __str__(self):
        return "\n".join([line for line in self._fsm_strgen()])

    def _fsm_strgen(self):
        yield "{0!r} {1!r}:".format(self.__class__.__name__, self._fsm_name)
        if len(self._fsm_transitions) == 0:
            yield "  (No states or transitions.)"
        for old_state, transitions in self._fsm_transitions.iteritems():
            yield "  {0!r}:".format(old_state)
            for input, result in transitions.iteritems():
                yield "    {0!r} -> {1!r}".format(
                    input, result[self.KeyNewState])
            yield ""
        yield "Current state: %r" % self._fsm_state

    def _fsm_startTimer(self, timer):
        pass

if __name__ == "__main__":
    import unittest
    import pdb
    logging.basicConfig(level=logging.DEBUG)

    class TestFSM(unittest.TestCase):

        def clock(self):
            return self._clock

        def setUp(self):
            self._clock = 0
            Timer.Clock = self.clock

        def testSimple(self):
            nf = FSM(name="testfsm")
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
            self.assertRaises(UnexpectedInput, lambda: nf.hit("stop"))

        def testTimer(self):
            nf = FSM(name="TestTimerFSM")

            self.retry = 0
            self.assertRaises(
                ValueError,
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
            self._clock = 10
            nf.checkTimers()
            self.assertEqual(self.retry, 2)
            self._clock = 15
            nf.checkTimers()
            self.assertEqual(self.retry, 2)

            # Timers are capable of being restarted, so we should be able to
            # restart.
            nf.hit("start")
            self._clock = 20
            nf.checkTimers()
            self.assertEqual(self.retry, 3)

            # Transition to running and check the timer is stopped.
            nf.hit("start_done")
            self._clock = 25
            nf.checkTimers()
            self.assertEqual(self.retry, 3)

    unittest.main()
