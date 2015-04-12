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
import Queue
import weakref
import logging
import _util
import retrythread

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
    KeyStartThreads = "start threads"
    KeyJoinThreads = "join threads"

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

    def __init__(self, name=None, asynchronous_timers=False):
        """name: a name for this FSM for debugging purposes.
        """
        log.debug("FSM init")
        super(FSM, self).__init__()

        if name is None:
            name = str(self.__class__.NextFSMNum)
            self.__class__.NextFSMNum += 1

        self._fsm_runningThreads = {}  # Dictionary keyed by thread name.
        self._fsm_oldThreads = []
        self._fsm_name = name
        self._fsm_use_async_timers = asynchronous_timers

        # Need to learn configuration from the class.
        class_transitions = self._fsm_transitions
        self._fsm_transitions = {}
        class_timers = self._fsm_timers
        self._fsm_timers = {}

        self._fsm_state = self._fsm_state

        # If the class had any pre-set transitions or timers, set them up now.
        for timer_name, (action, retryer) in class_timers.iteritems():
            self.addTimer(timer_name, action, retryer)

        # Ditto for transitions.
        for os, inp, ns, act, start_tmrs, stop_tmrs, strt_thrs, join_thrs in [
                (os, inp, result[self.KeyNewState],
                 result[self.KeyAction],
                 result[self.KeyStartTimers], result[self.KeyStopTimers],
                 result[self.KeyStartThreads], result[self.KeyJoinThreads])
                for os, state_trans in class_transitions.iteritems()
                for inp, result in state_trans.iteritems()]:
            self.addTransition(
                os, inp, ns, self._fsm_makeAction(act), start_tmrs, stop_tmrs,
                strt_thrs, join_thrs)

        self._fsm_inputQueue = Queue.Queue()

        if asynchronous_timers:
            # If we pass ourselves directly to the RetryThread, then we'll get
            # a retain deadlock so neither us nor the thread can be freed.
            # Fortunately python 2.7 has a nice weak references module.
            weak_self = weakref.ref(self)

            self._fsm_onThread = False

            def check_weak_self_timers():
                strong_self = weak_self()
                if strong_self is not None:
                    strong_self._fsm_backgroundTimerPop()

            self._fsm_thread = retrythread.RetryThread(
                action=check_weak_self_timers)

            # Initialize support for the _util.OnlyWhenLocked decorator.
            self._lock = threading.RLock()
            self._lock_holdingThread = None
            self._fsm_thread.start()

    def __del__(self):
        log.debug("Deleting FSM")
        if self._fsm_use_async_timers:
            self._fsm_thread.cancel()
            self._fsm_thread.join()

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
                      start_timers=None, stop_timers=None,
                      start_threads=None, join_threads=None):
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
        timrs_dict = self._fsm_timers

        trans_dict = self._fsm_transitions
        if old_state not in trans_dict:
            state_trans = {}
        else:
            state_trans = trans_dict[old_state]

        if input in state_trans:
            log.debug(self)
            raise ValueError(
                "FSM %r already has a transition for input %r into state "
                "%r." %
                (self._fsm_name, input, old_state))

        result = {}
        result[self.KeyNewState] = new_state
        result[self.KeyAction] = self._fsm_makeAction(action)

        result[self.KeyStartThreads] = (
            [] if start_threads is None else
            [self._fsm_makeAction(thr) for thr in start_threads])

        result[self.KeyJoinThreads] = (
            join_threads if join_threads is not None else [])

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

        # No exceptions, so update state.
        state_trans[input] = result
        trans_dict[old_state] = state_trans

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
    @_util.OnlyWhenLocked
    def setState(self, state):
        "Force set the state, perhaps to initialize it."
        if state not in self._fsm_transitions:
            raise ValueError(
                "FSM %r has no state %r so it cannot be set." %
                self._fsm_name, state)
        self._fsm_state = state

    def addFDSource(self, fd, action):
        if not self._fsm_use_async_timers:
            raise AttributeError(
                "FD sources only supported with asynchronous FSMs.")

        self._fsm_thread.addInputFD(fd, action)

    def rmFDSource(self, fd):
        if not self._fsm_use_async_timers:
            raise AttributeError(
                "FD sources only supported with asynchronous FSMs.")

        self._fsm_thread.rmInputFD(fd)

    def hit(self, input, *args, **kwargs):
        """Hit the FSM with input `input`.

        args and kwargs are passed through to the action.
        """
        log.debug("Queuing input %r", input)
        self._fsm_inputQueue.put((input, args, kwargs))

        if self._fsm_use_async_timers and not self._fsm_onThread:
            self._fsm_thread.addRetryTime(Timer.Clock())
        else:
            self._fsm_backgroundTimerPop()

    @_util.OnlyWhenLocked
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

        if not isinstance(action, str):
            raise ValueError("Action %r not a callable nor a method name." %
                             (action,))
        if not hasattr(self, action):
            raise ValueError(
                "Action %r is not a callable or a method on %r object." %
                (action, self.__class__.__name__))

        # Have to be careful not to retain ourselves, so use weak references.
        new_action = getattr(self, action)
        if not isinstance(new_action, collections.Callable):
            raise ValueError(
                "Action %r is not a callable or a method on %r object." %
                (action, self.__class__.__name__))

        weak_self = weakref.ref(self)

        def weak_action(*args, **kwargs):
            strong_self = weak_self()
            if strong_self is not None:
                getattr(strong_self, action)(*args, **kwargs)

        return weak_action

    @_util.OnlyWhenLocked
    def _fsm_hit(self, input, *args, **kwargs):
        """When the FSM is hit, the following actions are taken in the
        following order:

        1. Join any threads we're expecting to join.
        2. Stop any timers we're expecting are running.
        3. Update the state.
        4. Start any timers for the transition.
        5. Start any threads.
        6. If there are any old threads, tidy them up.
        """
        log.debug("_fsm_hit %r %r %r", input, args, kwargs)
        trans = self._fsm_transitions[self._fsm_state]
        if input not in trans:
            raise UnexpectedInput(
                "Input %r to %r %r (current state %r)." %
                (input, self.__class__.__name__, self._fsm_name,
                 self._fsm_state))
        res = trans[input]
        log.debug("%r: %r -> %r", self._fsm_state, input, res)

        for thrname in res[self.KeyJoinThreads]:
            if thrname not in self._fsm_runningThreads:
                log.warning(
                    "FSM %r could not stop thread %r on transition %r: %r -> "
                    "%r as it was not running.",
                    self._fsm_name, thrname, input, self.state,
                    res[self.KeyNewState])
                continue

            log.debug("join thread %r", thrname)
            thr = self._fsm_runningThreads.pop(thrname)

            if thr is threading.currentThread():
                log.debug("Can't join current thread; leave for later.")
                self._fsm_oldThreads.append(thr)
            else:
                thr.join()

        for st in res[self.KeyStopTimers]:
            log.debug("Stop timer %r", st.name)
            st.stop()

        self._fsm_state = res[self.KeyNewState]

        action = res[self.KeyAction]
        if action is not None:
            log.debug("Run transition's action %r", action)
            try:
                action(*args, **kwargs)
            except Exception as exc:
                log.exception("Hit exception processing FSM action %r." %
                              action)

        for st in res[self.KeyStartTimers]:
            log.debug("Start timer %r", st.name)
            st.start()
            if self._fsm_use_async_timers:
                self._fsm_thread.addRetryTime(st.nextPopTime)

        for thrAction in res[self.KeyStartThreads]:
            log.debug("Start thread %r", thrAction)
            thrname = thrAction.__name__
            thrThread = threading.Thread(target=thrAction, name=thrname)
            thrThread.start()
            if thrname in self._fsm_runningThreads:
                self._fsm_oldThreads.append(
                    self._fsm_runningThreads.pop(thrname))

            self._fsm_runningThreads[thrname] = thrThread

        # Remove old threads. This is in reverse order so that we can just
        # remove the indexes as we find them.
        for index, oldthread in zip(
                range(len(self._fsm_oldThreads) - 1, 0, -1),
                self._fsm_oldThreads[::-1]):

            if oldthread.isAlive():
                log.warning("Old thread %r still alive.", oldthread.name)
                continue

            log.debug("Join old thread %r", oldthread.name)

            if oldthread is threading.currentThread():
                log.debug("Can't join current thread; leave for later.")
                continue

            oldthread.join()
            del self._fsm_oldThreads[index]

        log.debug("Done hit.")

    def _fsm_backgroundTimerPop(self):
        log.debug("_fsm_backgroundTimerPop")
        try:
            self._fsm_onThread = True

            while not self._fsm_inputQueue.empty():
                input, args, kwargs = self._fsm_inputQueue.get()
                try:
                    self._fsm_hit(input, *args, **kwargs)
                finally:
                    self._fsm_inputQueue.task_done()

            self.checkTimers()
        finally:
            self._fsm_onThread = False