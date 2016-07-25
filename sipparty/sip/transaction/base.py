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

log = logging.getLogger(__name__)


@add_metaclass(ABCMeta)
class TransactionUser(object):
    """This is what Transaction Users must look like."""

    @abstractmethod
    def request(self, msg, transaction):
        """Consume a request passed up from the transaction.

        :param msg: The request to consume.
        :param transaction:
            The transaction. The TU should act on the response by forming a
            response and calling `transaction.respond(response)`.
        """
        raise NotImplemented

    @abstractmethod
    def response(self, msg):
        """Consume a response passed up from the transaction.

        :param msg: The response to consume.
        """

    @abstractmethod
    def transport_error(self, error):
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
            }
        }),
        AsyncFSM):
    """Base class for all SIP transactions."""

    types = Enum(('client', 'server', 'oneshot'))

    # States common to all transactions.
    Inputs = Enum(('request', 'transport_error'))
    States = Enum(('proceeding', 'completed', 'terminated'))

    # Default action on entering terminated state is to inform the TU.
    FSMStateEntryActions = (
        (States.terminated, ('inform_tu', 'transaction_terminated')),
    )

    # Default timer durations (seconds)
    T1 = 0.5
    T2 = 4
    T4 = 5

    @property
    def type(self):
        raise NotImplemented

    def __init__(self, *args, **kwargs):
        log.info('New %s instance', type(self).__name__)
        super(Transaction, self).__init__(*args, **kwargs)

        self.last_message = None

    #
    # ---------------------------- TRANSPORT INTERFACE ------------------------
    #
    def consume_message(self, message):
        if message.isrequest():
            if message.type == 'ACK':
                return self.hit('ack', message)
            return self.hit('request', message)

        inp = self.__most_specific_input_for_inbound_response(message.type)
        return self.hit(inp, message)

    #
    # ---------------------------- TU INTERFACE -------------------------------
    #
    def respond(self, message):
        inp = self.__most_specific_input_for_outbound_response(message.type)
        self.hit(inp, message)

    #
    # ---------------------------- FSM ACTIONS --------------------------------
    #
    def giveup(self):
        self.hit('timer_giveup')

    def inform_tu(self, method_name, *args, **kwargs):
        tu = self.transaction_user
        if tu is None:
            raise TypeError(
                'No transaction user set on the %s instance' % (
                    type(self).__name__))

        getattr(tu, method_name)(*args, **kwargs)

    def retransmit(self):
        log.debug('resend message')
        self.transmit(self.last_message)

    def transmit(self, message):
        log.debug('send %s message', message.type)
        self.last_message = message
        self.transport.send_message(
            message, self.remote_name, self.remote_port)

    #
    # ---------------------------- STANDARD TIMERS ----------------------------
    #
    StandardTimers = Enum((
        'standard_timer_retransmit_gen', 'standard_timer_giveup_gen',
        'standard_timer_stop_squelching_gen'))

    def standard_timer_retransmit_gen(self):
        """Yield intervals for standard retransmit timer as per RFC3261.

        https://tools.ietf.org/html/rfc3261#section-17.2.1

        After parsing that, the algorithm turns out to be quite simple.
        """
        next_interval = self.T1
        while True:
            yield next_interval
            next_interval *= 2
            next_interval = min(next_interval, self.T2)

    def standard_timer_giveup_gen(self):
        """Yield the standard giveup interval as per RFC3261.

        https://tools.ietf.org/html/rfc3261#section-17.2.1
        """
        yield 64 * self.T1

    def standard_timer_stop_squelching_gen(self):
        """Yield the giveup interval for timer I as per RFC3261.

        https://tools.ietf.org/html/rfc3261#section-17.2.1
        """
        yield self.T4

    #
    # ---------------------------- MAGIC METHODS ------------------------------
    #
    def __del__(self):
        log.debug('__del__ %s', type(self).__name__)
        getattr(super(Transaction, self), '__del__', lambda: None)()

    #
    # ---------------------------- INTERNAL METHODS ---------------------------
    #
    def __most_specific_input_for_inbound_response(self, rtype):
        return self.__most_specific_input_for_response('response_', rtype)

    def __most_specific_input_for_outbound_response(self, rtype):
        return self.__most_specific_input_for_response('respond_', rtype)

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
            if inp in self.Inputs:
                return inp
            next_rtype /= 10

        # Try catch all.
        inp = prepend + 'xxx'
        if inp in self.Inputs:
            return inp

        # Couldn't find one. Raise.
        raise UnexpectedInput(
            'No response input for prepend %s code %s' % (prepend, rtype,))
