"""fsm.py

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
import threading
import weakref
import logging
import _util

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
            raise ValueError("retryer is not a generator or iterable.")

        self._tmr_retryer = retry_generator
        self._tmr_currentPauseIter = None
        self._tmr_action = action
        self._tmr_startTime = None
        self._tmr_alarmTime = None

    def __repr__(self):
        return "Timer(%r, action=%r, retryer=%r)" % (
            self._tmr_name, self._tmr_action, self._tmr_retryer)

    @property
    def isRunning(self):
        # If the timer is running. A timer stops automatically after all the
        # pauses have been tried.
        return self._tmr_startTime is not None

    @property
    def nextPopTime(self):
        return self._tmr_alarmTime

    def start(self):
        "Start the timer."
        log.debug("Start timer %r.", self._tmr_name)
        self._tmr_startTime = self.Clock()
        self._tmr_currentPauseIter = self._tmr_retryer()
        self._tmr_setNextPopTime()

    def stop(self):
        "Stop the timer."
        self._tmr_startTime = None
        self._tmr_alarmTime = None
        self._tmr_currentPauseIter = None

    def check(self):
        "Checks the timer, and if it has expired runs the action."
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

    #
    # INTERNAL METHODS FOLLOW.
    #
    def _tmr_setNextPopTime(self):
        "Sets up the next pop time."
        if not self.isRunning:
            # Not running (perhaps the number of times to retry expired).
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
        "Pops this timer, calling the action."
        log.debug("POP, action %r", self._tmr_action)
        if self._tmr_action is not None:
            res = self._tmr_action()
        else:
            res = None
        return res


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


class FSM(object):
    """Interface:

    Class:
    `AddClassTransitions` - for subclassing; if a subclass declares this then
    it is called when the class is created (using the FSMType metaclass) and
    is used to set up the standard transitions and timers for a class.

    Class or instance:
    `addTimer` - add a timer that the transitions can control. If called as a
    class method, the timer is not created, but will be for each instance when
    they are.
    `addTransition` - add a transition.
    `setState` - set the state. Use in the `AddClassTransitions` method when
    subclassing to set the initial state. Can use on instances too for testing
    purposes but not recommended generally (as timers etc. will not be
    affected probably causing internal state to become inconsistent).

    Instance only:
    `hit` - hit with an input. Pass args and kwargs for the action if
    necessary.

    `checkTimers` - see if any of the timers need popping. Needs to be called
    manually if asynchronous_timers are not in use.
    """

    KeyNewState = "new state"
    KeyAction = "action"
    KeyStartTimers = "start timers"
    KeyStopTimers = "stop timers"

    NextFSMNum = 1

    class FSMType(type):
        def __init__(self, *args, **kwargs):
            type.__init__(self, *args, **kwargs)

            self._fsm_transitions = {}
            self._fsm_timers = {}
            self._fsm_name = self.__name__
            self._fsm_state = None

            # Add any predefined transitions.
            self.AddClassTransitions()

    __metaclass__ = FSMType

    def onlyWhenLocked(method):
        "This is a decorator and should not be called as a method."
        def maybeGetLock(self, *args, **kwargs):
            if not isinstance(self, type) and self._fsm_use_async_timers:
                with self._fsm_lock:
                    return method(self, *args, **kwargs)
            return method(self, *args, **kwargs)
        return maybeGetLock

    def __init__(self, name=None, asynchronous_timers=False):
        """name: a name for this FSM for debugging purposes.
        """
        log.debug("FSM init")
        super(FSM, self).__init__()

        if name is None:
            name = str(self.__class__.NextFSMNum)
            self.__class__.NextFSMNum += 1

        self._fsm_name = name

        # Need to learn configuration from the class.
        class_transitions = self._fsm_transitions
        self._fsm_transitions = {}
        class_timers = self._fsm_timers
        self._fsm_timers = {}

        self._fsm_state = self._fsm_state

        self._fsm_use_async_timers = asynchronous_timers

        # If the class had any pre-set transitions or timers, set them up now.
        for timer_name, (action, retryer) in class_timers.iteritems():
            self.addTimer(timer_name, action, retryer)

        # Ditto for transitions.
        for os, inp, ns, act, start_tmrs, stop_tmrs in [
                (os, inp, result[self.KeyNewState],
                 result[self.KeyAction],
                 result[self.KeyStartTimers], result[self.KeyStopTimers])
                for os, state_trans in class_transitions.iteritems()
                for inp, result in state_trans.iteritems()]:
            self.addTransition(
                os, inp, ns, self._fsm_makeAction(act), start_tmrs, stop_tmrs)

        if asynchronous_timers:
            # If we pass ourselves directly to the RetryThread, then we'll get
            # a retain deadlock so neither us nor the thread can be freed.
            # Fortunately python 2.7 has a nice weak references module.
            weak_self = weakref.ref(self)

            def check_weak_self_timers():
                strong_self = weak_self()
                if strong_self is not None:
                    strong_self.checkTimers()

            self._fsm_thread = RetryThread(
                action=check_weak_self_timers)
            self._fsm_lock = threading.RLock()
            self._fsm_thread.start()

    def __del__(self):
        log.debug("Deleting FSM")
        if self._fsm_use_async_timers:
            self._fsm_thread.cancel()

    def __str__(self):
        return "\n".join([line for line in self._fsm_strgen()])

    @property
    def state(self):
        return self._fsm_state

    @classmethod
    def AddClassTransitions(cls):
        """Subclasses should override this to do initial subclass setup. It
        is called when initializing the metaclass.
        """
        pass

    @_util.class_or_instance_method
    def addTransition(self, old_state, input, new_state, action=None,
                      start_timers=None, stop_timers=None):
        """Can be called either as class method or an instance method. Use as
        a class method if you are going to use a lot of instances of the FSM.

        old_state: the state from which to transition.
        input: the input to trigger this transition.
        new_state: the state into which to transition
        action: the action to perform when doing this transition (no args).
        start_timers: list of timer names to start when doing this transition
        (must have already been added with addTimer).
        stop_timers: list of timer names to stop when doing this transition
        (must have already been added with addTimer).
        """
        log.debug("addTransition self: %r", self)

        self_is_class = isinstance(self, type)
        trans_dict = self._fsm_transitions
        timrs_dict = self._fsm_timers

        if old_state not in trans_dict:
            trans_dict[old_state] = {}

        state_trans = trans_dict[old_state]

        if input in state_trans:
            log.debug(self)
            raise ValueError(
                "FSM %r already has a transition for input %r into state "
                "%r." %
                (self._fsm_name, input, old_state))

        result = {}
        state_trans[input] = result
        result[self.KeyNewState] = new_state
        result[self.KeyAction] = self._fsm_makeAction(action)

        # Link up the timers.
        for key, timer_names in (
                (self.KeyStartTimers, start_timers),
                (self.KeyStopTimers, stop_timers)):

            if self_is_class:
                # If we're the class, just store the names. They will be
                # converted into Timer instances when instances are created.
                result[key] = timer_names if timer_names is not None else []
                continue

            timers = []
            result[key] = timers

            if timer_names is None:
                # No timers specified, so leave a blank list.
                continue

            for timer_name in timer_names:
                if timer_name not in timrs_dict:
                    raise ValueError("No such timer %r." % (timer_name))
                timers.append(timrs_dict[timer_name])

        # For convenience assume that the first transition set tells us the
        # initial state.
        if not self_is_class and self._fsm_state is None:
            self.setState(old_state)

        log.debug("%r: %r -> %r", old_state, input, result[self.KeyNewState])

    @_util.class_or_instance_method
    def addTimer(self, name, action, retryer):
        """Add a timer with name `name`. Timers must be independent of
        transitions because they may be stopped or started at any transition.
        """
        newtimer = (
            (action, retryer) if isinstance(self, type) else
            Timer(name, self._fsm_makeAction(action), retryer))
        self._fsm_timers[name] = newtimer

    @_util.class_or_instance_method
    @onlyWhenLocked
    def setState(self, state):
        "Force set the state, perhaps to initialize it."
        if state not in self._fsm_transitions:
            raise ValueError(
                "FSM %r has no state %r so it cannot be set." %
                self._fsm_name, state)
        self._fsm_state = state

    @onlyWhenLocked
    def hit(self, input, *args, **kwargs):
        """Hit the FSM with input `input`.

        args and kwargs are passed through to the action.
        """
        trans = self._fsm_transitions[self._fsm_state]
        if input not in trans:
            raise UnexpectedInput(
                "Input %r to %r %r (current state %r)." %
                (input, self.__class__.__name__, self._fsm_name,
                 self._fsm_state))
        res = trans[input]
        log.debug("%r: %r -> %r", self._fsm_state, input, res)

        # Try `action` first; if this raises then we won't have updated the
        # FSM... This is to make testing easier. If the opposite behaviour is
        # desired then it might make sense to customize this class to support
        # optionally soldiering on if `action` raises.
        action = res[self.KeyAction]
        if action is not None:
            log.debug("Run transition's action %r", action)
            action(*args, **kwargs)

        for st in res[self.KeyStopTimers]:
            st.stop()

        self._fsm_state = res[self.KeyNewState]

        for st in res[self.KeyStartTimers]:
            st.start()
            if self._fsm_use_async_timers:
                self._fsm_thread.addRetryTime(st.nextPopTime)

    @onlyWhenLocked
    def checkTimers(self):
        "Check all the timers that are running."
        for name, timer in self._fsm_timers.iteritems():
            if timer.isRunning:
                timer.check()
                if self._fsm_use_async_timers:
                    self._fsm_thread.addRetryTime(timer.nextPopTime)

    #
    # INTERNAL METHODS FOLLOW.
    #
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

    @_util.class_or_instance_method
    def _fsm_makeAction(self, action):
        """action is either a callable, which is called directly, or it is a
        method name, in which case we bind it to a method if we can.
        """
        log.debug("make action %r", action)

        if action is None:
            return None

        if isinstance(action, collections.Callable):
            return action

        if isinstance(self, type):
            # Delay deciding whether the action is appropriate because we
            # can't bind the action name to a method at this point as we are
            # the class not the instance.
            return action

        if not hasattr(self, action):
            raise ValueError(
                "Action %r is not a callable or a method on %r object." %
                (action, self.__class__.__name__))

        new_action = getattr(self, action)
        if not isinstance(new_action, collections.Callable):
            raise ValueError(
                "Action %r is not a callable or a method on %r object." %
                (action, self.__class__.__name__))

        return new_action

if __name__ == "__main__":
    import unittest
    logging.basicConfig(level=logging.DEBUG)

    class TestFSM(unittest.TestCase):

        def wait_for(self, func, timeout=2):
            now = time.clock()
            until = now + timeout
            while time.clock() < until:
                if func():
                    break
            else:
                self.assertTrue(0, "Timed out waiting for %r" % func)

        def clock(self):
            return self._clock

        def setUp(self):
            self._clock = 0
            Timer.Clock = self.clock
            RetryThread.Clock = self.clock
            self.retry = 0
            self.cleanup = 0

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
            nf = FSM(name="TestAsyncFSM", asynchronous_timers=True)

            retry = [0]

            # Check trying to create a timer with a time that isn't iterable
            # ("1") fails.
            self.assertRaises(
                ValueError,
                lambda: Timer("retry", lambda: self, 1))

            def pop_func():
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
            self._clock = 0.1
            log.debug("clock incremented")
            self.wait_for(lambda: retry[0] == 1)

        def testActions(self):
            nf = FSM(name="TestActionsFSM", asynchronous_timers=True)

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
            self.assertEqual(actnow_hit[0], 1)

            actnext_hit = [0]

            def actnext(arg1):
                actnext_hit[0] += 1

            nf.addTransition("running", "stop", "stopped", action=actnext)
            self.assertRaises(TypeError, lambda: nf.hit("stop"))
            nf.hit("stop", 1)
            self.assertEqual(actnext_hit[0], 1)

        def testFSMClass(self):

            actnow_hit = [0]

            def actnow(*args, **kwargs):
                actnow_hit[0] += 1

            class FSMTestSubclass(FSM):

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

            class FSMTestBadSubclass(FSM):
                @classmethod
                def AddClassTransitions(cls):
                    log.debug("Test bad method.")
                    cls.addTimer("retry_start", "not-a-method",
                                 [1, 1, 1])

            self.assertRaises(ValueError, lambda: FSMTestBadSubclass())

    unittest.main()
