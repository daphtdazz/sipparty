"""Client SIP transactions.

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


class ClientTransaction(Transaction):
    """Base class for client transactions."""

    type = Transaction.types.client


class InviteClientTransaction(ClientTransaction):
    """Invite transaction specialization.

    RFC3261.17 says that the invite transaction must include ACKs to non-200
    responses, but does not include ACKs to the 200, which must be handled by
    the UAC, due to the importance of delivering 200s to the UAC.

    Upshot: the Invite Transaction state machine does not include ACKs to 200s!

    TU below is the Transaction User.
    """

    States = ClientTransaction.States | Enum(('calling',))
    Inputs = ClientTransaction.Inputs | Enum((
        'a_timer_retry', 'b_timer_giveup', 'd_timer_stop_response_squelching',
        'response_1', 'response_2', 'response_xxx', 'timer_completed'))
    FSMTimers = {
        'a_timer_retry': (
            'retransmit',
            Transaction.StandardTimers.standard_timer_retransmit_gen),
        'b_timer_giveup': (
            [('hit', Inputs.b_timer_giveup)],
            Transaction.StandardTimers.standard_timer_giveup_gen),
        'd_timer_stop_response_squelching': (
            [('hit', 'd_timer_stop_response_squelching')],
            'd_timer_stop_response_squelching_gen'),
    }
    FSMDefinitions = {
        InitialState: {
            Inputs.request: {
                tsk.NewState: States.calling,
                tsk.Action: 'transmit',
                tsk.StartTimers: ['a_timer_retry', 'b_timer_giveup'],
            },
        },
        States.calling: {
            Inputs.a_timer_retry: {
                tsk.Action: 'retransmit'
            },
            Inputs.b_timer_giveup: {
                tsk.NewState: States.terminated,
                tsk.Action: [
                    ('inform_tu', 'timeout',
                     TransactionTimeout('No response to INVITE')),
                ],
                tsk.StopTimers: ['a_timer_retry', 'b_timer_giveup'],
            },
            Inputs.response_1: {
                tsk.NewState: States.proceeding,
                tsk.StopTimers: ['a_timer_retry', 'b_timer_giveup'],
            },
            Inputs.response_2: {
                tsk.NewState: States.terminated,
                tsk.Action: (('inform_tu', 'response'),),
                tsk.StopTimers: ['a_timer_retry', 'b_timer_giveup'],
            },
            Inputs.response_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: (('inform_tu', 'response'), 'ack'),
                tsk.StopTimers: ['a_timer_retry', 'b_timer_giveup'],
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
                tsk.StopTimers: ['a_timer_retry', 'b_timer_giveup'],
            },
        },
        States.proceeding: {
            Inputs.response_1: {
                tsk.Action: [('inform_tu', 'response')],
            },
            Inputs.response_2: {
                tsk.NewState: States.terminated,
                tsk.Action: (('inform_tu', 'response'),),
            },
            Inputs.response_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: [('inform_tu', 'response'), 'ack'],
                tsk.StartTimers: ['d_timer_stop_response_squelching'],
            },
        },
        States.completed: {
            Inputs.d_timer_stop_response_squelching: {
                tsk.NewState: States.terminated,
                tsk.StopTimers: ['d_timer_stop_response_squelching'],
            },
            Inputs.response_xxx: {
                tsk.Action: 'ack',
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
                tsk.StopTimers: ['d_timer_stop_response_squelching'],
            },
        },
        States.terminated: {}
    }

    def d_timer_stop_response_squelching_gen(self):
        yield min(self.MIN_, )


class NonInviteClientTransaction(ClientTransaction):

    States = ClientTransaction.States | Enum(('trying',))
    Inputs = ClientTransaction.Inputs | Enum((
        'e_timer_retry', 'f_timer_giveup',
        'k_timer_stop_response_squelching',
        'response_1', 'response_2', 'response_xxx'))
    FSMTimers = {
        'e_timer_retry': ('retransmit', 'e_timer_retransmit_gen'),
        'f_timer_giveup': (
            [('hit', Inputs.f_timer_giveup)],
            Transaction.StandardTimers.standard_timer_giveup_gen),
        'k_timer_stop_response_squelching': (
            [('hit', 'k_timer_stop_response_squelching')],
            Transaction.StandardTimers.standard_timer_stop_squelching_gen),
    }
    FSMDefinitions = {
        InitialState: {
            Inputs.request: {
                tsk.NewState: States.trying,
                tsk.Action: 'transmit',
                tsk.StartTimers: ['e_timer_retry', 'f_timer_giveup'],
            },
        },
        States.trying: {
            Inputs.e_timer_retry: {
                tsk.Action: 'retransmit',
            },
            Inputs.f_timer_giveup: {
                tsk.NewState: States.terminated,
                tsk.Action: [
                    ('inform_tu', 'timeout',
                     TransactionTimeout(
                         'No response to request received at all'))],
                tsk.StopTimers: ['e_timer_retry', 'f_timer_giveup'],
            },
            Inputs.response_1: {
                tsk.NewState: States.proceeding,
                tsk.Action: [('inform_tu', 'response')],
            },
            Inputs.response_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: [('inform_tu', 'response')],
                tsk.StopTimers: ['e_timer_retry', 'f_timer_giveup'],
                tsk.StartTimers: ['k_timer_stop_response_squelching'],
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
                tsk.StopTimers: ['e_timer_retry', 'f_timer_giveup'],
            },
        },
        # This state may look identical to States.trying, but it is subtly
        # different in the retransmit timer behaviour, see
        # e_timer_retransmit_gen.
        States.proceeding: {
            Inputs.e_timer_retry: {
                tsk.Action: 'retransmit',
            },
            Inputs.f_timer_giveup: {
                tsk.NewState: States.terminated,
                tsk.Action: [
                    ('inform_tu', 'timeout',
                     TransactionTimeout(
                         'No final response to request received'))],
                tsk.StopTimers: ['e_timer_retry', 'f_timer_giveup'],
            },
            Inputs.response_1: {
                tsk.Action: [('inform_tu', 'response')],
            },
            Inputs.response_xxx: {
                tsk.NewState: States.completed,
                tsk.Action: [('inform_tu', 'response')],
                tsk.StopTimers: ['e_timer_retry', 'f_timer_giveup'],
                tsk.StartTimers: ['k_timer_stop_response_squelching'],
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated,
                tsk.Action: [('inform_tu', 'transport_error')],
                tsk.StopTimers: ['e_timer_retry', 'f_timer_giveup'],
            },
        },
        States.completed: {
            Inputs.k_timer_stop_response_squelching: {
                tsk.NewState: States.terminated,
                tsk.StopTimers: ['k_timer_stop_response_squelching'],
            },
            Inputs.response_xxx: {},
        },
        States.terminated: {}
    }

    def e_timer_retransmit_gen(self):
        """Yield intervals between the retransmit timer E as per RFC3261.

        This is different from the standard timer for retransmit because
        it is state dependent, to slow down responses quicker when we have
        received a provisional response.

        https://tools.ietf.org/html/rfc3261#section-17.1.2.2
        """
        next_interval = self.T1
        while True:
            yield next_interval
            if self.state == self.States.proceeding:
                next_interval = self.T2
                continue

            next_interval *= 2
            next_interval = min(next_interval, self.T2)
