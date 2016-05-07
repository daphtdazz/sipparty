"""State machines to control SIP transactions.

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
from abc import ABCMeta, abstractmethod
import logging
from numbers import Real

from six import add_metaclass

from ..deepclass import (dck, DeepClass)
from ..transport import IsValidPortNum
from ..util import Enum, WeakProperty
from ..fsm import (AsyncFSM, InitialStateKey as InitialState, tsk)
from .prot import (
    DefaultMaximumRetryTimeMS, DefaultRetryTimeMS, TransactionID)

log = logging.getLogger(__name__)


class TransactionError(Exception):
    pass


class TransactionManager(object):

    lookup_sentinel = type('TransactionManagerLookupSentinel', (), {})()

    @classmethod
    def transaction_key_for_message(cls, msg):
        """Return a key for the message to look up its transaction.

        :param message: The message to generate a key for.
        :returns tuple:
            A key in the form of a tuple suitable for looking in
            `self.transactions`.
        """
        return TransactionID(
            msg.ViaHeader.parameters.branch.value, msg.CseqHeader.reqtype)

    def __init__(self):
        """Initialization method.

        :param args:
        """
        self.transactions = {}

    def __del__(self):
        log.info('__del__ TransactionManager')
        getattr(
            super(TransactionManager, self), '__del__', lambda: None)()

    def add_transaction_for_message(self, trans, message):
        tk = self.transaction_key_for_message(message)
        self.transactions[tk] = trans

    def lookup_transaction(self, message, default=lookup_sentinel):
        """Lookup a transaction for a message.

        :returns Transaction,None:
        """
        assert default is self.lookup_sentinel
        tk = self.transaction_key_for_message(message)
        try:
            return self.transactions[tk]
        except KeyError as exc:
            exc.args = ((
                '%s; message type %s' % (exc.args[0], message.type),) +
                exc.args[1:])
            raise

    def new_transaction_for_request(self, req, transport, transaction_user,
                                    **kwargs):

        if req.type == 'INVITE':
            trns = InviteClientTransaction(**kwargs)
        else:
            trns = NonInviteClientTransaction(**kwargs)

        trns.transport = transport
        trns.transaction_user = transaction_user
        self.add_transaction_for_message(trns, req)
        return trns


@add_metaclass(ABCMeta)
class TransactionUser(object):
    """This is what Transaction Users must look like."""

    @abstractmethod
    def consumeMessage(self, msg, tu_data=None):
        """Consume a message passed up from the transaction.

        :param msg: The message to consume.
        :param tu_data:
            The data the transaction user passed in (if any) when it created
            the transaction.
        """
        raise NotImplemented


@add_metaclass(ABCMeta)
class TransactionTransport(object):
    """This is what a transport object for the transaction must look like."""

    @abstractmethod
    def send_message(self, msg, tt_data=None):
        """Send a SIP message.

        :param msg: The message to send.
        :param tt_data:
            Some transport data / correlator that the transport can use to send
            the message more efficiently, which may or may not be set on the
            Transaction.
        """
        raise NotImplemented


class Transaction(
        DeepClass('_trns_', {
            'transaction_user': {
                dck.descriptor: WeakProperty,
                dck.check: lambda x: isinstance(x, TransactionUser)
            },
            'transport': {
                dck.descriptor: WeakProperty,
                dck.check: lambda x: isinstance(x, TransactionTransport)
            },
            'remote_name': {
                dck.check: lambda x: isinstance(x, str)
            },
            'remote_port': {
                dck.check: IsValidPortNum
            },
            'tu_data': {},
            'tt_data': {}
        }),
        AsyncFSM):

    def __init__(self, *args, **kwargs):
        super(Transaction, self).__init__(*args, **kwargs)

        self.last_message = None

    def __del__(self):
        log.info('__del__ %s', type(self).__name__)
        getattr(super(Transaction, self), '__del__', lambda: None)()

    """Base class for all SIP transactions."""
    def send_message(self, message):
        log.debug('send %s message', message.type)
        self.last_message = message
        self.transport.send_message(
            message, self.remote_name, self.remote_port)

    def resend_message(self):
        msg = self.last_message
        assert msg is not None, (
            "Can't resend in a transaction before the first send.")
        log.debug('resend message %s', msg.type)
        self.send_message(msg)

    def giveup(self):
        self.hit('timer_giveup')


class ClientTransaction(
        DeepClass("_sipt_", {
            'initial_retry_period_ms': {
                dck.gen: lambda: DefaultRetryTimeMS,
                dck.check: lambda x: isinstance(x, Real) and x > 0
            },
            'maximum_retry_period_ms': {
                dck.gen: lambda: DefaultMaximumRetryTimeMS,
                dck.check: lambda x: isinstance(x, Real) and x > 0
            }
        }),
        Transaction):
    """Base class for client transactions."""

    States = Enum(('trying', 'proceeding', 'completed', 'terminated'))
    Inputs = Enum((
        'request', 'transport_error', 'timer_retry', 'timer_giveup',
        '_1xx', '_2xx', '_3_6xx', 'timer_completed'))
    FSMTimers = {
        'timer_retry': ('resend_message', 'timer_retry_gen'),
        'timer_giveup': ('giveup', 'timer_giveup_gen'),
        # 'timer_completed': ('complete', 'timer_completed_gen')
    }

    giveup_period_multiple = 64

    @property
    def giveup_period(self):
        return (
            self.initial_retry_period_ms * self.giveup_period_multiple /
            1000.0)

    def timer_retry_gen(self):
        total_wait = 0
        next_wait = self.initial_retry_period_ms / 1000.0
        while total_wait + next_wait < self.giveup_period:
            yield next_wait
            total_wait += next_wait

            # The duration of the timer double each reattempt, as per
            # https://tools.ietf.org/html/rfc3261#section-17.1.1.2
            next_wait = next_wait * 2
            if next_wait > self.maximum_retry_period_ms / 1000.0:
                next_wait = self.maximum_retry_period_ms / 1000.0

    def timer_giveup_gen(self):
        yield self.giveup_period


class NonInviteClientTransaction(ClientTransaction):
    States = ClientTransaction.States
    Inputs = ClientTransaction.Inputs
    Actions = Enum(('send',))
    FSMDefinitions = {
        InitialState: {
            Inputs.request: {
                tsk.NewState: States.trying,
                tsk.StartTimers: ['timer_retry', 'timer_giveup'],
                tsk.Action: ['send_message']
            },
        },
        States.trying: {
            Inputs.timer_retry: {
                # Send request
            },
            Inputs.timer_giveup: {

                tsk.NewState: States.terminated,
                tsk.StopTimers: ['timer_retry', 'timer_giveup']
                # Inform TU, inform manage, 'timer_completed'r.
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated
                # Inform TU, inform manager.
            },
            Inputs._2xx: {
                tsk.NewState: States.terminated
                # Pass to TU, inform manager.
            },
            Inputs._1xx: {
                tsk.NewState: States.proceeding
                # Pass to TU
            },
            Inputs._3_6xx: {
                tsk.NewState: States.completed
                # Send ACK, pass to TU.
            }
        },
        States.proceeding: {
            Inputs._1xx: {
                # Pass to TU
            },
            Inputs._2xx: {
                tsk.NewState: States.terminated
                # Pass to TU, inform manager.
            },
            Inputs._3_6xx: {
                tsk.NewState: States.completed
                # Send ACK, Pass to TU.
            },
        },
        States.completed: {
            Inputs.transport_error: {
                tsk.NewState: States.terminated
                # Inform TU, inform manager.
            },
            Inputs._3_6xx: {
                # Send ACK
            },
            Inputs.timer_giveup: {
                tsk.NewState: States.terminated
                # Inform manager
            }
        },
        States.terminated: {}
    }


class InviteClientTransaction(ClientTransaction):
    """Invite transaction specialization.

    RFC3261.17 says that the invite transaction must include ACKs to non-200
    responses, but does not include ACKs to the 200, which must be handled by
    the UAC, due to the importance of delivering 200s to the UAC.

    Upshot: the Invite Transaction state machine does not include ACKs to 200s!

    TU below is the Transaction User.
    """
    Inputs = ClientTransaction.Inputs
    States = ClientTransaction.States
    FSMDefinitions = {
        InitialState: {
            Inputs.request: {
                tsk.NewState: States.trying,
                # Send INVITE
            },
        },
        States.trying: {
            Inputs.timer_retry: {
                # Send INVITE
            },
            Inputs.timer_giveup: {
                tsk.NewState: States.terminated
                # Inform TU, inform manager.
            },
            Inputs.transport_error: {
                tsk.NewState: States.terminated
                # Inform TU, inform manager.
            },
            Inputs._2xx: {
                tsk.NewState: States.terminated
                # Pass to TU, inform manager.
            },
            Inputs._1xx: {
                tsk.NewState: States.proceeding
                # Pass to TU
            },
            Inputs._3_6xx: {
                tsk.NewState: States.completed
                # Send ACK, pass to TU.
            }
        },
        States.proceeding: {
            Inputs._1xx: {
                # Pass to TU
            },
            Inputs._2xx: {
                tsk.NewState: States.terminated
                # Pass to TU, inform manager.
            },
            Inputs._3_6xx: {
                tsk.NewState: States.completed
                # Send ACK, Pass to TU.
            },
        },
        States.completed: {
            Inputs.transport_error: {
                tsk.NewState: States.terminated
                # Inform TU, inform manager.
            },
            Inputs._3_6xx: {
                # Send ACK
            },
            Inputs.timer_completed: {
                tsk.NewState: States.terminated
                # Inform manager
            }
        },
        States.terminated: {}
    }
