"""Implements an `FSM` for use with sip party.

This provides a generic way to implement arbitrary state machines, with easy
support for timers.

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
from collections import (Callable, Iterable, OrderedDict)
from copy import copy
from functools import partial
import logging
from six import iteritems
from six.moves import queue
import time
import threading
from weakref import ref
from ..classmaker import classbuilder
from ..util import (
    CCPropsFor, class_or_instance_method, Enum, OnlyWhenLocked)
from . import (fsmtimer, retrythread)

log = logging.getLogger(__name__)

__all__ = [
    'AsyncFSM', 'FSMError', 'UnexpectedInput', 'FSMTimeout', 'FSM',
    'FSMClassInitializer', 'InitialStateKey', 'LockedFSM', 'TransitionKeys',
    'tsk']


class FSMError(Exception):
    pass


class UnexpectedInput(FSMError):
    pass


class FSMTimeout(FSMError):
    pass


InitialStateKey = 'Initial'
TransitionKeys = Enum((
    'NewState',
    'Action',
    'StartTimers',
    'StopTimers',
    'StartThreads'
))
# Abbreviation for TransitionKeys
tsk = TransitionKeys


class FSMClassInitializer(type):
    def __init__(self, name, bases, dict_):
        super(FSMClassInitializer, self).__init__(name, bases, dict_)
        log.debug("FSMClass states after super init: %r",
                  None if not hasattr(self, "States") else self.States)

        self._fsm_transitions = {}
        self._fsm_timers = {}
        self._fsm_name = self.__name__
        self._fsm_state = InitialStateKey
        self._fsm_state_entry_actions = {}

        # Add any predefined timers.
        self.AddTimers()

        # Add any predefined transitions.
        self.AddClassTransitions()
        log.debug("FSMClass inputs / states after AddClassTransitions: %r / "
                  "%r", self.States, self.Inputs)

        # Add any predefined actions on state entry.
        self.AddActionsOnStateEntry()


@classbuilder(mc=(
    CCPropsFor(("States", "Inputs", "Actions")), FSMClassInitializer))
class FSM:
    """Interface:

    Class:
    `AddClassTransitions` - for subclassing; if a subclass declares this then
    it is called when the class is created (using the
    :py:class:`FSMClassInitializer` metaclass) and
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
    InitialStateKey = InitialStateKey
    KeyNewState = TransitionKeys.NewState
    KeyAction = TransitionKeys.Action
    KeyStartTimers = TransitionKeys.StartTimers
    KeyStopTimers = TransitionKeys.StopTimers
    KeyStartThreads = TransitionKeys.StartThreads

    NextFSMNum = 1

    # These are Cumulative Properties (see the metaclass).
    States = Enum((InitialStateKey,))
    Inputs = Enum(tuple())
    Actions = Enum(tuple())

    @classmethod
    def delegate_method_name(cls, action_name):
        return 'fsm_dele_' + action_name

    @classmethod
    def PopulateWithDefinition(cls, definition_dict):
        cls._fsm_definitionDictionary = definition_dict
        for old_state, stdict in iteritems(definition_dict):
            for input, transdef in iteritems(stdict):
                ns = transdef.get(TransitionKeys.NewState, old_state)
                if ns not in definition_dict:
                    raise KeyError(
                        "NewState %r for input %r to state %r for "
                        "transitions definition dictionary for class %r "
                        "has not been declared in the dictionary." % (
                            ns, input, old_state, cls.__name__))

                cls.addTransition(
                    old_state, input, ns,
                    action=transdef.get(tsk.Action, None),
                    start_threads=transdef.get(tsk.StartThreads, None),
                    start_timers=transdef.get(tsk.StartTimers, None),
                    stop_timers=transdef.get(tsk.StopTimers, None))

    @classmethod
    def AddClassTransitions(cls):
        """Subclasses should override this to do initial subclass setup. It
        is called when initializing the metaclass.
        """
        if hasattr(cls, "FSMDefinitions"):
            cls.PopulateWithDefinition(cls.FSMDefinitions)

    @classmethod
    def AddTimers(cls):
        """Build and add the predefined timers."""
        tmrs = getattr(cls, 'FSMTimers', {})
        for tname, (act, retryer) in iteritems(tmrs):
            cls.addTimer(tname, act, retryer)

    @classmethod
    def AddActionsOnStateEntry(cls):
        state_acts = getattr(cls, 'FSMStateEntryActions', [])
        for state, act in state_acts:
            cls.add_action_on_state_entry(state, act)

    #
    # =================== CLASS OR INSTANCE INTERFACE ========================
    #
    @class_or_instance_method
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
        log.detail(
            "addTransition self: %r %s:%s->%s", self, input, old_state,
            new_state)

        self_is_class = isinstance(self, type)
        timrs_dict = self._fsm_timers

        trans_dict = self._fsm_transitions
        if old_state not in trans_dict:
            state_trans = OrderedDict()
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

        log.detail("  addTransition threads: %r", start_threads)
        result[self.KeyStartThreads] = (
            [] if start_threads is None else
            [self._fsm_makeThreadAction(thr) for thr in start_threads]
            if isinstance(start_threads, tuple) or
            isinstance(start_threads, list) else
            [self._fsm_makeThreadAction(start_threads)])

        # Link up the timers.
        for key, timer_names in (
                (self.KeyStartTimers, start_timers),
                (self.KeyStopTimers, stop_timers)):

            if self_is_class:
                # If we're the class, just store the names. They will be
                # converted into Timer instances when instances are created.
                result[key] = timer_names or []
                continue

            timers = []
            result[key] = timers

            if not timer_names:
                # No timers specified, so leave a blank list.
                continue

            for timer_name in timer_names:
                log.debug('Add timer %r to fsm %r', timer_name, self.name)
                if timer_name not in timrs_dict:
                    raise KeyError("No such timer %r." % (timer_name))
                timers.append(timrs_dict[timer_name])

        # No exceptions, so update state.
        state_trans[input] = result
        trans_dict[old_state] = state_trans

        if input not in self.Inputs:
            self.Inputs.add(input)

        for state in (old_state, new_state):
            if state not in self.States:
                self.States.add(state)

        log.detail("%r: %r -> %r", old_state, input, result[self.KeyNewState])

    @class_or_instance_method
    def addTimer(self, name, action, retryer):
        """Add a timer with name `name`.

        Timers must be independent of transitions because they may be stopped
        or started at any transition.
        """
        if isinstance(self, type):
            # Class, just save the parameters for when we instantiate and
            # create the actual generator and action then.
            self._fsm_timers[name] = (action, retryer)
            return

        if isinstance(retryer, str):

            weak_self = ref(self)
            retryer_name = retryer

            def weak_retry_wrapper():
                self = weak_self()
                if self is None:
                    log.warning(
                        'Retryer for timer %s has been released, returning '
                        'empty list of retry times', name)
                    return iter(())

                try:
                    retryer = getattr(self, retryer_name)
                except AttributeError as exc:
                    exc.args = (
                        "Can't make an action with string %s as it is not a "
                        "method;%s" % (retryer, exc.args[0]),)
                    raise

                return retryer()

            retryer = weak_retry_wrapper

        newtimer = fsmtimer.Timer(name, self._fsm_makeAction(action), retryer)
        self._fsm_timers[name] = newtimer

    @class_or_instance_method
    def add_action_on_state_entry(self, state, action):
        if state not in self.States:
            raise ValueError(
                'Cannot add action for entry into non-existent state %r' % (
                    state,))

        act_list = self._fsm_state_entry_actions.get(state)
        if act_list is None:
            act_list = []
            self._fsm_state_entry_actions[state] = act_list

        act_list.append(self._fsm_makeAction(action))

    #
    # =================== INSTANCE INTERFACE =================================
    #
    @property
    def name(self):
        return self._fsm_name

    @property
    def state(self):
        return self._fsm_state

    @state.setter
    def state(self, value):
        assert self._fsm_state == InitialStateKey, (
            "Only allowed to set the state of an FSM when it is in its "
            "initial state.")
        if value not in self.States:
            raise ValueError('State %r is not one of %r' % (
                value, self.States))
        self._fsm_state = value

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
            self._fsm_weakDelegate = ref(val)

    def __init__(self, name=None, delegate=None):
        """
        :param None,str name: a name for this FSM for debugging purposes. If
        `None`, then a name will be generated from the class name and a count
        of how many unnamed instances have been created so far.
        :param delegate: A delegate. If this delegate has method names that
        match actions, then they will be called when the action is called.
        """
        super(FSM, self).__init__()

        if name is None:
            name = '%s%s' % (self._fsm_name, self.__class__.NextFSMNum)
            self.__class__.NextFSMNum += 1

        self._fsm_name = name
        self._fsm_weakDelegate = None
        self.delegate = delegate
        self.__processing_hit = False

        # Need to learn configuration from the class.
        class_transitions = self._fsm_transitions
        self._fsm_transitions = OrderedDict()
        class_timers = self._fsm_timers
        self._fsm_timers = {}
        # It's important that the timers are scheduled predictably for
        # the case where timers are due to pop at the same time, so we need to
        # track the running timers in a list.
        self._fsm_running_timers = []
        self.Inputs = copy(self.Inputs)

        self._fsm_state = getattr(self, '_fsm_state')
        log.debug("Initial state of %r instance is %r.",
                  self.__class__.__name__, self._fsm_state)

        # If the class had any pre-set transitions or timers, set them up now.
        for timer_name, (action, retryer) in iteritems(class_timers):
            self.addTimer(timer_name, action, retryer)

        # Ditto for transitions.
        for os, inp, ns, act, start_tmrs, stop_tmrs, strt_thrs in [
                (os, inp, result[self.KeyNewState],
                 result[self.KeyAction],
                 result[self.KeyStartTimers], result[self.KeyStopTimers],
                 result[self.KeyStartThreads])
                for os, state_trans in iteritems(class_transitions)
                for inp, result in iteritems(state_trans)]:
            self.addTransition(
                os, inp, ns, act, start_tmrs, stop_tmrs, strt_thrs)

        class_state_entries = self._fsm_state_entry_actions
        self._fsm_state_entry_actions = {}
        for state, act in (
                (s, a) for s, acts in iteritems(class_state_entries)
                for a in acts):
            self.add_action_on_state_entry(state, act)

        self.__input_queue = queue.Queue()
        self._fsm_oldThreadQueue = queue.Queue()

        log.detail(
            "  %r instance after init: %r", self.__class__.__name__, self)
        return

    def checkTimers(self):
        "Check all the timers that are running."
        log.debug('check timers on fsm %s', self.name)
        for timer in self._fsm_running_timers:
            timer.check()

    def hit(self, input, *args, **kwargs):
        """Hit the FSM with `input`.

        It is illegal to hit an FSM during processing of an action, and this is
        guarded against. The reason for this is that it is not obvious whether
        or not the state should change before or after the actions are
        processed. If an action wishes to cause another FSM hit, it should use
        :py:method:`queue_hit`.

        args and kwargs are passed through to the action.
        """
        log.debug("Queuing input %r", input)

        self.__queue_next_hit((input, args, kwargs))
        self.__process_queued_hits()

    def raise_unexpected_input(self, input):
        raise(UnexpectedInput("%r instance fsm has no input %r." % (
            type(self).__name__, input)))

    def start_timer(self, timer):
        """Signals the timer that it should start.
        :param timer: The FSMTimer to start.

        Subclassing: subclasses may override this to implement background timer
        popping, which is what AsyncFSM does.
        """
        timer.start()

        # Don't re-add the timer if it's already there; we're allowed to
        # restart timers.
        if timer not in self._fsm_running_timers:
            self._fsm_running_timers.append(timer)

    def stop_timer(self, timer):
        """Signals the timer that it should stop.
        :param timer: The FSMTimer to stop.

        Subclassing: subclasses may override this to implement background timer
        popping tidy-up, which is what AsyncFSM does.
        """
        del self._fsm_running_timers[self._fsm_running_timers.index(timer)]
        timer.stop()

    #
    # ======================= INTERNAL METHODS ===============================
    #
    @class_or_instance_method
    def _fsm_makeAction(self, action):
        # action is either a callable, which is called directly, or it is a
        # method name, in which case we bind it to a method if we can.
        log.debug("make action %r", action)

        if action is None:
            return None

        # Normalize to a list of actions.
        if isinstance(action, str) or isinstance(action, Callable):
            action_list = [action]
        else:
            action_list = list(action)

        def _raise_ValueError():
            raise ValueError(
                "Action %r not a valid action type (must be a single action "
                "or list of actions, where an action is a method name or a "
                "Callable)." % (action,))

        if not isinstance(action_list, Iterable):
            _raise_ValueError()

        if any(
                not (
                    isinstance(_act, str) or isinstance(_act, Callable) or
                    isinstance(_act, list) or isinstance(_act, tuple))
                for _act in action_list):
            _raise_ValueError()

        if isinstance(self, type):
            # Delay actually building the action until we have an instance
            # for it.
            return action

        weak_self = ref(self)

        def weak_perform_actions(*args, **kwargs):
            """Find action to run if self is not released and run it.

            The Lookup order is:

            If self has a method with the correct name, it is run.
            If the delegate exists and has a method with the correct name, it
            is run too.
            If both were run, the result of the self method is returned.
            If just one was run, then the result of just that one is returned.

            Otherwise AttributeError is raised.
            """
            log.debug("Action list: %r", action_list)
            assert len(action_list)
            self = weak_self()
            if self is None:
                return None

            for action in action_list:
                run_delegate = False
                run_self = False
                run_callable = False

                if isinstance(action, Callable):
                    crv = action(*args, **kwargs)
                    run_callable = True
                    continue

                if isinstance(action, str):
                    action_name = action
                    action_partial_args = ()
                else:
                    action_name = action[0]
                    action_partial_args = action[1:]

                func = getattr(self, action_name, None)
                if isinstance(func, Callable):
                    log.debug(
                        'Call self.%s(*%s)', action_name, action_partial_args)
                    run_self = True
                    srv = partial(func, *action_partial_args)(*args, **kwargs)

                dele = getattr(self, "delegate", None)
                delegate_method_name = FSM.delegate_method_name(action_name)
                if dele is not None:
                    method = getattr(dele, delegate_method_name, None)
                    if isinstance(method, Callable):
                        log.debug(
                            "Call self.delegate.%s(*%s)", delegate_method_name,
                            action_partial_args)

                        run_delegate = True
                        drv = partial(method, self, *action_partial_args)(
                            *args, **kwargs)

                if not run_delegate:
                    # The delegate was not run, so see if we have a default
                    # delegate method.
                    method = getattr(self, delegate_method_name, None)
                    if isinstance(method, Callable):
                        log.debug(
                            "Call self.%s(*%s)", delegate_method_name,
                            action_partial_args)

                        run_delegate = True
                        drv = partial(method, *action_partial_args)(
                            *args, **kwargs)

                if not (run_self or run_delegate):
                    # The action could not be resolved.
                    raise AttributeError(
                        "Action {0!r} is not a callable or a method on the "
                        "{1} instance "
                        "(attribute value was {2}) and its delegate {3!r} "
                        "had no "
                        "such attribute and no default delegate method on "
                        "the {1!r} instance was implemented.".format(
                            action_name, self.__class__.__name__,
                            getattr(self, action_name, '<not present>'),
                            getattr(self, 'delegate', None)))

            del self
            if run_self:
                return srv

            if run_delegate:
                return drv

            if run_callable:
                return crv

            # It would be a bug to reach here.
            assert any((run_self, run_delegate, run_callable)), (
                "This is a bug. Actions shouldn't exist unless they have more "
                "than one subactions to perform.")

        weak_perform_actions.action_list = str(action_list)
        return weak_perform_actions

    @class_or_instance_method
    def _fsm_makeThreadAction(self, action):

        weak_method = self._fsm_makeAction(action)
        if isinstance(self, type):
            # Delay deciding whether the action is appropriate because we
            # can't bind the action name to a method at this point as we are
            # the class not the instance.
            return weak_method

        weak_self = ref(self)
        owner_thread = threading.currentThread()

        def fsmThread():
            cthr = threading.currentThread()
            log.debug("FSM Thread %r in.", cthr.name)
            while owner_thread.isAlive():
                self = weak_self()
                log.debug("Self is %r.", self)
                del self
                try:
                    wait = weak_method()
                except Exception:
                    log.exception("Exception in %r thread.", cthr.name)
                    break

                if wait is None:
                    break

                log.debug("Thread %r wants to try again in %02f seconds.",
                          cthr.name, wait)
                time.sleep(wait)
            else:
                log.warning(
                    "Owner thread died, so finishing FSM thread %r.",
                    cthr.name)

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

    def __str__(self):
        return "\n".join([line for line in self._fsm_strgen()])

    def _fsm_strgen(self):
        yield "{0!r} {1!r}:".format(self.__class__.__name__, self._fsm_name)
        if len(self._fsm_transitions) == 0:
            yield "  (No transitions.)"
        for old_state, transitions in iteritems(self._fsm_transitions):
            yield "  {0!r}:".format(old_state)
            for input, result in iteritems(transitions):
                yield "    {0!r} -> {1!r}".format(
                    input, result[self.KeyNewState])
            yield ""
        yield "Current state: %r" % self._fsm_state

    def __queue_next_hit(self, hit_tuple):
        self.__input_queue.put(hit_tuple)

    def __process_queued_hits(self):
        if self.__processing_hit:
            log.debug(
                '%s %s already processing hits', type(self).__name__,
                self.name)
            return

        while not self.__input_queue.empty():
            input, args, kwargs = self.__input_queue.get()
            log.debug("Process input %r.", input)
            try:
                self.__processing_hit = True
                self._fsm_hit(input, *args, **kwargs)
            finally:
                self.__processing_hit = False
                log.debug("Items left on queue: %d",
                          self.__input_queue.qsize())

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
        log.detail("_fsm_hit %r %r %r", input, args, kwargs)

        old_state = self._fsm_state
        ts = self._fsm_transitions

        def BadInput():
            msg = "Bad input %r to %r instance %r (current state %r)." % (
                input, self.__class__.__name__, self._fsm_name,
                old_state)
            log.error(msg)
            raise UnexpectedInput(msg)

        if old_state not in ts:
            BadInput()
        trans = ts[old_state]

        if input not in trans:
            BadInput()

        res = trans[input]
        new_state = res[self.KeyNewState]
        log.info(
            "FSM: %r; Input: %r; State Change: %r -> %r.",
            self._fsm_name, input, old_state, new_state)

        for st in res[self.KeyStopTimers]:
            self.stop_timer(st)

        # The action is complex; see _fsm_makeAction.
        action = res[self.KeyAction]
        if action is not None:
            log.debug("Run transition's action %r", action)
            try:
                action(*args, **kwargs)
            except Exception as exc:
                log.error("Hit %s processing FSM actions %r: %s" % (
                    type(exc).__name__, action.action_list, exc))
                raise

        for st in res[self.KeyStartTimers]:
            self.start_timer(st)

        for thrAction in res[self.KeyStartThreads]:
            log.info("Starting FSM thread: %r.", thrAction.name)
            thrname = thrAction.name
            thrThread = threading.Thread(target=thrAction, name=thrname)
            thrThread.start()

        # It is only when everything has succeeded that we know we can update
        # the state.
        self._fsm_setState(new_state)

        # Perform actions registered for state entry.
        acts = self._fsm_state_entry_actions.get(new_state, ())
        for act in acts:
            act(*args, **kwargs)

        log.debug("Done hit.")

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

    @class_or_instance_method
    def _fsm_setState(self, new_state):
        "Should only be called from methods that have the lock."
        self._fsm_state = new_state


class LockedFSM(FSM):

    def __init__(self, *args, **kwargs):
        """Protects
        """
        super(LockedFSM, self).__init__(*args, **kwargs)
        self._lock = None

        # We should lock access to this FSM's state as it may be called
        # from multiple threads.
        # Initialize support for the util.OnlyWhenLocked decorator.
        self._lock = threading.RLock()
        self._lock_holdingThread = None
        self._fsm_stateChangeCondition = threading.Condition(self._lock)

        log.detail('LockedFSM after init: %r', self)

    hit = OnlyWhenLocked(FSM.hit, allow_recursion=True)


class AsyncFSM(LockedFSM):

    def __init__(self, *args, **kwargs):
        super(AsyncFSM, self).__init__(*args, **kwargs)

        # If we pass ourselves directly to the RetryThread, then we'll get
        # a retain deadlock so neither us nor the thread can be freed.
        # Fortunately python 2.7 has a nice weak references module.
        weak_self = ref(self)

        def check_weak_self_timers():
            self = weak_self()
            if self is None:
                return

            self.__backgroundTimerPop()

        self._fsm_thread = retrythread.RetryThread()
        self._fsm_thread.add_action(check_weak_self_timers)

    def start_timer(self, timer):
        """Override of the superclass to implement background timer scheduling.

        :param timer: The FSMTimer to start.
        """
        super(AsyncFSM, self).start_timer(timer)
        self._fsm_thread.addRetryTime(timer.nextPopTime)

    def checkTimers(self):
        """Check all the timers."""
        for timer in self._fsm_running_timers:
            # Squelch the exception if the timer isn't running yet, because
            # that's easier than checking each one first.
            timer.check(exception_if_not_running=False)
            if timer.nextPopTime is not None:
                self._fsm_thread.addRetryTime(timer.nextPopTime)

    def waitForStateCondition(self, condition, timeout=5):
        if not isinstance(condition, Callable):
            raise TypeError(
                'condition %r can not be called so can\'t be waited for to '
                'become True.' % condition)

        now = time.time()
        then = now + (timeout if timeout is not None else 0)
        with self._fsm_stateChangeCondition:
            while timeout is None or then > now:
                state = self._fsm_state
                if condition(state):
                    break
                self._fsm_stateChangeCondition.wait(then - now)
                now = time.time()
            else:
                raise FSMTimeout("Timeout waiting for condition.")

    def addFDSource(self, fd, action):
        self._fsm_thread.addInputFD(fd, action)

    def rmFDSource(self, fd):
        self._fsm_thread.rmInputFD(fd)

    def __del__(self):
        log.info("DELETE FSM %s", self.name)
        getattr(super(AsyncFSM, self), '__del__', lambda: None)()

    @class_or_instance_method
    def _fsm_setState(self, new_state):
        with self._fsm_stateChangeCondition:
            super(AsyncFSM, self)._fsm_setState(new_state)
            self._fsm_stateChangeCondition.notify_all()

    def __backgroundTimerPop(self):
        log.debug("__backgroundTimerPop")
        self.checkTimers()
        self._fsm_garbageCollect()
