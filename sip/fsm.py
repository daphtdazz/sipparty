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
import six
import collections
import time
import timeit
import threading
import Queue
import weakref
import copy
import logging
import _util
import retrythread
import fsmtimer

if __name__ == "__main__":
    logging.basicConfig()
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)
    log.setLevel(logging.INFO)


class FSMError(Exception):
    pass


class UnexpectedInput(FSMError):
    pass


class FSMTimeout(FSMError):
    pass


def block_until_states(states):
    "Decorator factory to block waiting for an FSM transition."
    log.debug("Create block until for %r.", states)

    def buse_desc(method):
        def block_until_states_wrapper(self, *args, **kwargs):
            state_now = self.state
            log.debug("Block after %r for %.2f secs until %r.",
                      method.__name__, self._tfsm_timeout, states)
            method(self, *args, **kwargs)

            end_states = states
            time_start = _util.Clock()
            time_now = time_start
            while self.state not in end_states:
                if time_now - time_start > self._tfsm_timeout:
                    log.error(
                        "Timeout (after %f seconds) waiting for states %r",
                        self._tfsm_timeout, states)
                    self.hit(self.States.error)
                    new_end_states = (self.States.error,)
                    if end_states == new_end_states:
                        raise FSMError(
                            "help failed to enter error state.")
                    end_states = new_end_states
                    time_start = time_now

                time.sleep(0.00001)
                time_now = _util.Clock()

            if self.state not in end_states:
                raise FSMTimeout("Timeout reaching end state.")
        return block_until_states_wrapper
    return buse_desc

InitialStateKey = "Initial"
TransitionKeys = _util.Enum((
    "NewState",
    "Action"
    ))


class FSMClassInitializer(type):
        def __init__(self, name, bases, dict):
            super(FSMClassInitializer, self).__init__(name, bases, dict)
            log.debug("FSMClass states after super init: %r",
                      None if not hasattr(self, "States") else self.States)

            self._fsm_transitions = {}
            self._fsm_timers = {}
            self._fsm_name = self.__name__
            self._fsm_state = None

            # Add any predefined transitions.
            self.AddClassTransitions()
            log.debug("FSMClass states after AddClassTransitions: %r",
                      self.States)
            log.debug("FSMClass inputs after AddClassTransitions: %r",
                      self.Inputs)


@six.add_metaclass(
    # The FSM type needs both the FSMClassInitializer and the cumulative
    # properties tool.
    type('FSMType',
         (_util.CCPropsFor(("States", "Inputs", "Actions")),
          FSMClassInitializer),
         dict()))
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

    #
    # =================== CLASS INTERFACE ====================================
    #
    KeyNewState = "new state"
    KeyAction = "action"
    KeyStartTimers = "start timers"
    KeyStopTimers = "stop timers"
    KeyStartThreads = "start threads"

    NextFSMNum = 1

    # These are Cumulative Properties (see the metaclass).
    States = _util.Enum(tuple())
    Inputs = _util.Enum(tuple())
    Actions = _util.Enum(tuple())

    @classmethod
    def PopulateWithDefinition(cls, definition_dict):
        cls._fsm_definitionDictionary = definition_dict
        for old_state, stdict in six.iteritems(definition_dict):
            for input, transdef in six.iteritems(stdict):
                try:
                    ns = transdef[TransitionKeys.NewState]
                except KeyError:
                    raise KeyError(
                        "FSM definition transition dictionary for "
                        "input {input!r} into state {old_state!r} doesn't "
                        "have a {ns!r} value."
                        "".format(ns=TransitionKeys.NewState, **locals()))
                if ns not in definition_dict:
                    raise KeyError(
                        "NewState %r for input %r to state %r for "
                        "transitions definition dictionary for class %r "
                        "has not been declared in the dictionary." % (
                            ns, input, old_state, cls.__name__))
                action = (
                    transdef[TransitionKeys.Action]
                    if TransitionKeys.Action in transdef else
                    None)

                cls.addTransition(old_state, input, ns, action=action)

        # If the special initial state is specified, set that.
        if InitialStateKey in definition_dict:
            cls.setState(InitialStateKey)

    @classmethod
    def AddClassTransitions(cls):
        """Subclasses should override this to do initial subclass setup. It
        is called when initializing the metaclass.
        """
        pass

    #
    # =================== CLASS OR INSTANCE INTERFACE ========================
    #
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
            [self._fsm_makeThreadAction(thr) for thr in start_threads])

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

        if input not in self.Inputs:
            self.Inputs.add(input)

        for state in (old_state, new_state):
            if state not in self.States:
                self.States.add(state)

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
            fsmtimer.Timer(name, self._fsm_makeAction(action), retryer))
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

    #
    # =================== INSTANCE INTERFACE =================================
    #
    @property
    def state(self):
        return self._fsm_state

    @property
    def delegate(self):
        if self._fsm_weakDelegate is None:
            return None
        return self._fsm_weakDelegate()

    @delegate.setter
    def delegate(self, val):
        if val is None:
            self._fsm_weakDelegate = None
        else:
            self._fsm_weakDelegate = weakref.ref(val)

    def __init__(self, name=None, asynchronous_timers=False, delegate=None):
        """name: a name for this FSM for debugging purposes.
        """
        log.debug("FSM init")
        super(FSM, self).__init__()

        if name is None:
            name = self._fsm_name + six.binary_type(self.__class__.NextFSMNum)
            self.__class__.NextFSMNum += 1

        self._fsm_name = name
        self._fsm_use_async_timers = asynchronous_timers
        self._fsm_weakDelegate = None
        self.delegate = delegate

        # Need to learn configuration from the class.
        class_transitions = self._fsm_transitions
        self._fsm_transitions = {}
        class_timers = self._fsm_timers
        self._fsm_timers = {}
        self.Inputs = copy.copy(self.Inputs)

        self._fsm_state = self._fsm_state

        # If the class had any pre-set transitions or timers, set them up now.
        for timer_name, (action, retryer) in six.iteritems(class_timers):
            self.addTimer(timer_name, action, retryer)

        # Ditto for transitions.
        for os, inp, ns, act, start_tmrs, stop_tmrs, strt_thrs in [
                (os, inp, result[self.KeyNewState],
                 result[self.KeyAction],
                 result[self.KeyStartTimers], result[self.KeyStopTimers],
                 result[self.KeyStartThreads])
                for os, state_trans in six.iteritems(class_transitions)
                for inp, result in six.iteritems(state_trans)]:
            self.addTransition(
                os, inp, ns, self._fsm_makeAction(act), start_tmrs, stop_tmrs,
                strt_thrs)

        self._fsm_inputQueue = Queue.Queue()
        self._fsm_oldThreadQueue = Queue.Queue()

        if asynchronous_timers:
            # If we pass ourselves directly to the RetryThread, then we'll get
            # a retain deadlock so neither us nor the thread can be freed.
            # Fortunately python 2.7 has a nice weak references module.
            weak_self = weakref.ref(self)

            def check_weak_self_timers():
                self = weak_self()
                if self is None:
                    log.debug("Weak check timers has been released.")
                    return
                log.debug("Weak check timers has not been released.")

                self._fsm_backgroundTimerPop()

            self._fsm_thread = retrythread.RetryThread(
                action=check_weak_self_timers)

            # Initialize support for the _util.OnlyWhenLocked decorator.
            self._lock = threading.RLock()
            self._lock_holdingThread = None

            self._fsm_thread.start()

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

        self._fsm_popTimerNow()

    @_util.OnlyWhenLocked
    def checkTimers(self):
        "Check all the timers that are running."
        for name, timer in six.iteritems(self._fsm_timers):
            isRunning = timer.isRunning
            log.debug("Check timer %r (isRunning: %r).", name, isRunning)
            if isRunning:
                timer.check()
                if self._fsm_use_async_timers:
                    self._fsm_thread.addRetryTime(timer.nextPopTime)

    #
    # ======================= INTERNAL METHODS ===============================
    #
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

        weak_self = weakref.ref(self)

        def weak_action(*args, **kwargs):
            log.debug("Weak action %r.", action)
            self = weak_self()
            if self is None:
                return None

            run_delegate = False
            run_self = False
            if hasattr(self, action):
                log.debug("  Self has %r.", action)
                func = getattr(self, action)
                if isinstance(func, collections.Callable):
                    run_self = True
                    srv = func(*args, **kwargs)

            if hasattr(self, "delegate"):
                dele = getattr(self, "delegate")
                if dele is not None:
                    if hasattr(dele, action):
                        log.debug("  delegate has %r.", action)
                        method = getattr(dele, action)
                        run_delegate = True
                        drv = method(*args, **kwargs)

            if run_self:
                del self
                return srv
            if run_delegate:
                del self
                return drv

            # Else the action could not be resolved.
            raise ValueError(
                "Action %r is not a callable or a method on %r object or "
                "its delegate %r." %
                (action, self.__class__.__name__,
                 self.delegate
                 if hasattr(self, "delegate") else None))

        weak_action.__name__ = "weak_action_" + six.binary_type(action)
        return weak_action

    @_util.class_or_instance_method
    def _fsm_makeThreadAction(self, action):

        weak_method = self._fsm_makeAction(action)
        if isinstance(self, type):
            # Delay deciding whether the action is appropriate because we
            # can't bind the action name to a method at this point as we are
            # the class not the instance.
            return weak_method

        weak_self = weakref.ref(self)

        def fsmThread():
            cthr = threading.currentThread()
            log.debug("FSM Thread %r in.", cthr.name)
            while True:
                self = weak_self()
                log.debug("Self is %r.", self)
                del self
                try:
                    wait = weak_method()
                except Exception as exc:
                    log.exception("Exception in %r thread.", cthr.name)
                    break

                if wait is None:
                    break

                log.debug("Thread %r wants to try again in %02f seconds.",
                          cthr.name, wait)
                time.sleep(wait)

            self = weak_self()
            if self is not None:
                log.debug(
                    "Thread %r finishing, put on FSM's old thread queue.",
                    cthr.name)
                self._fsm_oldThreadQueue.put(cthr)
                # Do not pop the timer now, because this could attempt to
                # garbage collect another thread also attempting to garbage
                # collect, leading to a deadlock.
                # self._fsm_popTimerNow()
            log.debug("FSM Thread %r out.", cthr.name)

        fsmThread.name = str(action)
        return fsmThread

    def __del__(self):
        log.debug("Deleting FSM")
        if self._fsm_use_async_timers:
            self._fsm_thread.cancel()
            if self._fsm_thread is not threading.currentThread():
                self._fsm_thread.join()

    def __str__(self):
        return "\n".join([line for line in self._fsm_strgen()])

    def _fsm_strgen(self):
        yield "{0!r} {1!r}:".format(self.__class__.__name__, self._fsm_name)
        if len(self._fsm_transitions) == 0:
            yield "  (No states or transitions.)"
        for old_state, transitions in six.iteritems(self._fsm_transitions):
            yield "  {0!r}:".format(old_state)
            for input, result in six.iteritems(transitions):
                yield "    {0!r} -> {1!r}".format(
                    input, result[self.KeyNewState])
            yield ""
        yield "Current state: %r" % self._fsm_state

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
            msg = "Bad input %r to %r %r (current state %r)." % (
                input, self.__class__.__name__, self._fsm_name,
                self._fsm_state)
            log.error(msg)
            raise UnexpectedInput(msg)
        res = trans[input]
        new_state = res[self.KeyNewState]
        log.info(
            "FSM: %r; Input: %r; State Change: %r -> %r.",
            self._fsm_name, input, self._fsm_state, new_state)

        for st in res[self.KeyStopTimers]:
            log.debug("Stop timer %r", st.name)
            st.stop()

        self._fsm_state = new_state

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
            log.info("Starting FSM thread: %r.", thrAction.name)
            thrname = thrAction.name
            thrThread = threading.Thread(target=thrAction, name=thrname)
            thrThread.start()

        log.debug("Done hit.")

    def _fsm_popTimerNow(self):
        if self._fsm_use_async_timers:
            self._fsm_thread.addRetryTime(_util.Clock())
        else:
            self._fsm_backgroundTimerPop()

    def _fsm_backgroundTimerPop(self):
        log.debug("_fsm_backgroundTimerPop")

        while not self._fsm_inputQueue.empty():
            input, args, kwargs = self._fsm_inputQueue.get()
            log.debug("Process input %r.", input)
            try:
                self._fsm_hit(input, *args, **kwargs)
            finally:
                self._fsm_inputQueue.task_done()
                log.debug("Items left on queue: %d",
                          self._fsm_inputQueue.qsize())

        self.checkTimers()
        self._fsm_garbageCollect()

    def _fsm_garbageCollect(self):

        selfthr = threading.currentThread()
        while not self._fsm_oldThreadQueue.empty():
            thr = self._fsm_oldThreadQueue.get()

            # Garbage collection from the garbage collectable FSM threads is
            # illegal as that can cause deadlocks between two separate FSM
            # threads attempting to collect each other.
            assert thr is not selfthr

            log.debug("Joining thread %r", thr.name)
            thr.join()
            log.debug("Joined thread %r", thr.name)
