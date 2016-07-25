"""Server SIP transactions.

Copyright 2016 David Park

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

from ...util import Enum
from ...fsm import InitialStateKey as InitialState, tsk
from .base import Transaction
from .errors import TransactionTimeout

log = logging.getLogger(__name__)


class ServerTransaction(Transaction):
    """Base class for server transactions"""

    type = Transaction.types.server
    Inputs = Transaction.Inputs | Enum((
        'ack', 'respond_1', 'respond_2', 'respond_xxx',))


class InviteServerTransaction(ServerTransaction):
    """Server Transaction for an INVITE request."""

    Inputs = ServerTransaction.Inputs | Enum((
        'h_timer_giveup', 'i_timer_stop_squelching'))
    States = ServerTransaction.States | Enum(('confirmed',))
    FSMTimers = {
        'g_timer_retransmit': (
            'retransmit',
            Transaction.StandardTimers.standard_timer_retransmit_gen),
        'h_timer_giveup': (
            [('hit', Inputs.h_timer_giveup)],
            Transaction.StandardTimers.standard_timer_giveup_gen),
        'i_timer_stop_ack_squelching': (
            [('hit', Inputs.i_timer_stop_squelching)],
            Transaction.StandardTimers.standard_timer_stop_squelching_gen),
    }
    FSMDefinitions = {
        InitialState: {
            Inputs.request: {
                tsk.NewState: States.proceeding,
                tsk.Action: (('inform_tu', 'request'),),
            },
        },
        States.proceeding: {
            Inputs.request: {
                tsk.Action: 'retransmit'
            },
            Inputs.respond_1: {
                tsk.Action: 'transmit'
            },
            Inputs.respond_2: {
                tsk.NewState: States.terminated,
                tsk.Action: 'transmit'
            },
            Inputs.respond_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: 'transmit',
                tsk.StartTimers: ['g_timer_retransmit', 'h_timer_giveup']
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: (('inform_tu', 'transport_error'),)
            }
        },
        States.completed: {
            Inputs.request: {
                tsk.Action: 'retransmit'
            },
            Inputs.ack: {
                tsk.NewState: States.confirmed,
                tsk.StopTimers: ['g_timer_retransmit', 'h_timer_giveup'],
            },
            Inputs.h_timer_giveup: {
                tsk.NewState: States.terminated,
                tsk.Action: [(
                    'inform_tu', 'timeout',
                    TransactionTimeout('No ACK to negative response'))],
                tsk.StopTimers: ['g_timer_retransmit', 'h_timer_giveup'],
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
                tsk.StartTimers: ['i_timer_stop_ack_squelching'],
                tsk.StopTimers: ['g_timer_retransmit', 'h_timer_giveup'],
            },
        },
        States.confirmed: {
            Inputs.ack: {},
            Inputs.i_timer_stop_squelching: {
                tsk.NewState: States.terminated,
                tsk.StopTimers: ['i_timer_stop_ack_squelching']
            }
        },
        States.terminated: {}
    }


class NonInviteServerTransaction(ServerTransaction):
    """Server Transaction for a non-INVITE request."""

    Inputs = ServerTransaction.Inputs | Enum((
        'j_timer_stop_retransmitting_responses',))
    States = ServerTransaction.States | Enum(('trying',))
    FSMTimers = {
        'j_timer_stop_retransmitting_responses': (
            [('hit', Inputs.j_timer_stop_retransmitting_responses)],
            Transaction.StandardTimers.standard_timer_giveup_gen),
    }
    FSMDefinitions = {
        InitialState: {
            Inputs.request: {
                tsk.NewState: States.trying,
                tsk.Action: [('inform_tu', 'request')],
            },
        },
        States.trying: {
            Inputs.respond_1: {
                tsk.NewState: States.proceeding,
                tsk.Action: 'transmit',
            },
            Inputs.respond_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: 'transmit',
                tsk.StartTimers: ['j_timer_stop_retransmitting_responses'],
            },
        },
        States.proceeding: {
            Inputs.request: {
                tsk.Action: 'retransmit',
            },
            Inputs.respond_1: {
                tsk.Action: 'transmit',
            },
            Inputs.respond_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: 'transmit',
                tsk.StartTimers: ['j_timer_stop_retransmitting_responses'],
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
            },
        },
        States.completed: {
            Inputs.request: {
                tsk.Action: 'retransmit',
            },
            Inputs.j_timer_stop_retransmitting_responses: {
                tsk.NewState: States.terminated,
                tsk.StopTimers: ['j_timer_stop_retransmitting_responses'],
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
                tsk.StopTimers: ['j_timer_stop_retransmitting_responses'],
            },
        },
        States.terminated: {},
    }
