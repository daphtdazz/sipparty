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

from six import add_metaclass

from ...deepclass import (dck, DeepClass)
from ...transport import IsValidPortNum
from ...util import Enum, WeakProperty
from ...fsm import AsyncFSM, UnexpectedInput
from ..standardtimers import StandardTimers
from .errors import NoTransport

log = logging.getLogger(__name__)


@add_metaclass(ABCMeta)
class TransactionUser(object):
    """This is what Transaction Users must look like."""

    @abstractmethod
    def consume_request(self, msg, transaction):
        """Consume a request passed up from the transaction.

        :param msg: The request to consume.
        :param transaction:
            The transaction. The TU should act on the response by forming a
            response and calling `transaction.respond(response)`.
        """
        raise NotImplemented

    @abstractmethod
    def consume_response(self, msg):
        """Consume a response passed up from the transaction.

        :param msg: The response to consume.
        """

    @abstractmethod
    def transport_error(self, error):
        raise NotImplemented

    @abstractmethod
    def timeout(self):
        raise NotImplemented


@add_metaclass(ABCMeta)
class TransactionTransport(object):
    """This is what a transport object for the transaction must look like."""

    @abstractmethod
    def send_message(self, msg):
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
            }
        }),
        StandardTimers,
        AsyncFSM):
    """Base class for all SIP transactions."""

    types = Enum(('client', 'server'))

    # States common to all transactions.
    Inputs = Enum(('request', 'transport_error'))
    States = Enum(('proceeding', 'completed', 'terminated'))

    @property
    def type(self):
        raise NotImplemented

    def __init__(self, *args, **kwargs):
        log.info('New %s instance', type(self).__name__)
        super(Transaction, self).__init__(*args, **kwargs)

        self.last_message = None
        self.last_socket = None
        self.retransmit_count = 0

    #
    # ---------------------------- TRANSPORT INTERFACE ------------------------
    #
    def consume_message(self, message):
        if message.isrequest():
            if message.type == 'ACK':
                return self.hit('ack', message)
            return self.hit(self.Inputs.request, message)
        return self.hit('response_' + str(message.type), message)

    #
    # ---------------------------- TU INTERFACE -------------------------------
    #
    def request(self, message, **kwargs):
        return self.hit(self.Inputs.request, message, **kwargs)

    def respond(self, message, **kwargs):
        return self.hit('respond_' + str(message.type), message, **kwargs)

    def handle_outbound_message(self, message, **kwargs):
        if message.isrequest():
            return self.request(message, **kwargs)
        return self.respond(message, **kwargs)

    #
    # ---------------------------- FSM ACTIONS --------------------------------
    #
    def giveup(self):
        self.hit('timer_giveup')

    def inform_tu(self, method_name, *args, **kwargs):
        tu = self.transaction_user
        if tu is None:
            log.warning(
                'No transaction user set on %s instance, inform action %s is '
                'not being honoured.', type(self).__name__, method_name)
            return

        getattr(tu, method_name)(*args, **kwargs)

    def retransmit(self, msg=None):
        """Retransmit the last response.

        :param req:
            a message may be passed in if we're handling this as a result of
            receiving a retransmission, but we ignore it.
        """
        log.debug('resend message')
        msg = self.last_message
        if msg is None:
            log.warning(
                '%s.retransmit called but no previous message',
                type(self).__name__
            )
            return
        self.transmit(msg)
        self.retransmit_count += 1

    def transmit(self, message, remote_name=None, remote_port=None):
        log.debug('send %s message', message.type)
        self.last_message = message
        if remote_name is not None:
            log.debug('Update remote name: %s', remote_name)
            self.remote_name = remote_name
        if remote_port is not None:
            self.remote_port = remote_port
            log.debug('Update remote port: %s', remote_port)
        tp = self.transport
        if tp is None:
            self.hit(
                self.Inputs.transport_error,
                NoTransport('Transport has been deleted under us.'))
            return

        self.last_socket = tp.send_message(
            message, self.remote_name, self.remote_port)

    #
    # ---------------------------- OVERRIDES ---------------------------------
    #
    def _fsm_hit(self, input, *args, **kwargs):
        inp_type, _, code = input.partition('_')
        if _ and inp_type in ('response', 'respond'):
            input = self.__most_specific_input_for_response(
                inp_type + '_', code)

        super(Transaction, self)._fsm_hit(input, *args, **kwargs)

    #
    # ---------------------------- MAGIC METHODS -----------------------------
    #
    def __del__(self):
        log.debug('__del__ %s', type(self).__name__)
        getattr(super(Transaction, self), '__del__', lambda: None)()

    #
    # ---------------------------- INTERNAL METHODS --------------------------
    #
    def __most_specific_input_for_response(self, prepend, rtype):
        """Work out what input to use for the response type.

        :param prepend: Prepend on the input.
        :param rtype: Response number.

        E.g. for a transaction with inputs::

            ('response_200', 'response_4')

        `'response', 200` will find input `'response_200'`, `404` will find
        input `'response_4'`.
        """
        next_rtype = int(rtype)
        while next_rtype > 0:
            inp = prepend + str(next_rtype)
            if inp in self._fsm_transitions[self._fsm_state]:
                return inp
            next_rtype = int(next_rtype / 10)

        # Try catch all.
        inp = prepend + 'xxx'
        if inp in self._fsm_transitions[self._fsm_state]:
            return inp

        # Couldn't find one. Raise.
        raise UnexpectedInput(
            'No response input to %s fsm for prepend %s code %s' % (
                type(self).__name__, prepend, rtype,))
