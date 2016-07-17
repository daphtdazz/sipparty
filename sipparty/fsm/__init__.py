"""
Overview
--------
The FSM module provides a framework for writing Finite State Machines easily
and descriptively, both for use synchronously and asynchronously. It was
written for and is used heavily by the `sipparty`_ SIP implementation.

.. sipparty: index.html

FSM
---

The base FSM class implements the following function.

A FSM
~~~~~

An :py:class:`FSM` instance has a finite number of states, and a finite number
of inputs.

All FSMs have an ``'Initial'`` state which they are put in when they are
instantiated::

    from fsm import FSM

    my_fsm = FSM()
    assert my_fsm.state == 'Initial'

FSM instances can transition between states and perform various actions on
transitioning. To make an FSM act, the method hit() is used::

    my_fsm.hit(my_fsm.Inputs.start)

Each input for a particular state can have one or more of the following
effects.

1.  Transition

    The FSM moves from its current state into a new state.

2.  Action

    The FSM performs an action.

        *   If the action is a callable, the action is called with any
            arguments passed into the hit() method after the input name.
        *   If the action is a string, the FSM attempts to find a function to
            call with the action's name.

            1.  The FSM instance is asked for an attribute with the same
                name as the action. If one is found it is called.

                So this may be a method on the instance's class, allowing
                customisation through subclassing of FSM if desired.

            2.  The FSM instance is asked for an attribute called delegate.

                If one is found, it is asked for an attribute with the same
                name as the action. If found, that is called.

            Note that if both the FSM instance and its delegate have attributes
            with the same name as the action, both will be called.

        *   Invalid input.

3.  If no transition is found for the state / input pair,
    :py:exception:`UnexpectedInput` is raised.

..
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
from .fsm import (
    AsyncFSM, FSM, FSMTimeout, InitialStateKey, LockedFSM, TransitionKeys,
    tsk, UnexpectedInput)
from .retrythread import RetryThread
from .fsmtimer import Timer
