"""Manager for SIP transactions.

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

from ...util import WeakMethod, WeakProperty
from ..prot import TransactionID
from .base import Transaction
from .client import (
    InviteClientTransaction, NonInviteClientTransaction,
    OneShotClientTransaction)
from .server import (
    InviteServerTransaction, NonInviteServerTransaction,
    OneShotServerTransaction)

log = logging.getLogger(__name__)


class TransactionManager(object):

    lookup_sentinel = type('TransactionManagerLookupSentinel', (), {})()
    transport = WeakProperty('transport')

    @classmethod
    def transaction_key_for_message(cls, ttype, msg):
        """Return a key for the message to look up its transaction.

        :param message: The message to generate a key for.
        :returns tuple:
            A key in the form of a tuple suitable for looking in
            `self.transactions`.
        """
        assert ttype in Transaction.types
        bval = msg.ViaHeader.parameters.branch.value
        log.debug('bval is %s', bval)
        if not bval:
            raise ValueError(
                'Cannot create a transaction key from a message with no '
                'branch value')
        rtype = msg.CseqHeader.reqtype
        if not rtype:
            raise ValueError(
                'Cannot create a transaction key from a message with no '
                'request type')

        return TransactionID(ttype, bval, rtype)

    def __init__(self, transport):
        """Initialization method.

        :param args:
        """
        self.transport = transport
        self.transactions = {}
        self.terminated_transactions = {}

    def transaction_for_inbound_message(self, msg, **kwargs):
        if msg.isrequest():
            log.debug('Gt inbound server transaction for request %s', msg.type)
            trans = self.lookup_transaction(
                'server', msg, raise_on_missing=False)
            if trans is not None:
                log.debug('Got existing transaction')
                return trans

            return self._new_transaction('server', msg, **kwargs)

        log.debug('Get inbound client trans for response %d', msg.type)
        return self.lookup_transaction('client', msg)

    def transaction_for_outbound_message(self, msg, **kwargs):
        if msg.isrequest():
            log.debug('Get outbound client trans for request %s', msg.type)
            trans = self.lookup_transaction(
                'client', msg, raise_on_missing=False)
            if trans is not None:
                log.debug('Got existing transaction')
                return trans

            return self._new_transaction('client', msg, **kwargs)

        log.debug('Get outbound server trans for response %d', msg.type)
        trans = self.lookup_transaction('server', msg, raise_on_missing=False)
        if trans is not None:
            log.debug('Return existing server transaction for outbound msg')
            return trans

        return self._new_transaction('server', msg, **kwargs)

    def __del__(self):
        log.info('DELETE TransactionManager')
        getattr(
            super(TransactionManager, self), '__del__', lambda: None)()

    def add_transaction_for_message(self, ttype, message, trans):
        assert ttype in Transaction.types
        tk = self.transaction_key_for_message(ttype, message)
        self.transactions[tk] = trans
        trans.add_action_on_state_entry(
            trans.States.terminated,
            WeakMethod(self, 'transaction_terminated', static_args=(tk,)))

    def lookup_transaction(self, ttype, message, default=lookup_sentinel,
                           raise_on_missing=True):
        """Lookup a transaction for a message.

        :returns Transaction:

        :raises KeyError: if no transaction could be found.
        """
        assert default is self.lookup_sentinel
        tk = self.transaction_key_for_message(ttype, message)
        log.debug('lookup transaction for key %s', tk)
        trans = self.transactions.get(tk)
        if trans is None and raise_on_missing:
            raise KeyError(
                'No %s transaction for key %s, message type %s' % (
                    ttype, tk, message.type))
        return trans

    def transaction_terminated(self, key, *args, **kwargs):
        log.info('Dropping terminated transaction %s', key)
        del self.transactions[key]

    def _new_transaction(self, ttype, msg, **kwargs):
        assert ttype in Transaction.types

        # Call the appropriate specialist method.
        trans = getattr(self, '_new_transaction_' + ttype)(
            msg, transport=self.transport, **kwargs)
        self.add_transaction_for_message(ttype, msg, trans)
        return trans

    def _new_transaction_client(self, msg, **kwargs):
        assert msg.isrequest()
        if msg.type == msg.types.INVITE:
            return InviteClientTransaction(**kwargs)
        if msg.type == msg.types.ACK:
            return OneShotClientTransaction(**kwargs)
        return NonInviteClientTransaction(**kwargs)

    def _new_transaction_server(self, msg, **kwargs):

        if msg.type == msg.types.INVITE:
            log.debug('new INVITE server transaction')
            return InviteServerTransaction(**kwargs)
        if msg.type == msg.types.ACK:
            log.debug('new oneshot server transaction for ACK')
            return OneShotServerTransaction(**kwargs)

        if msg.isrequest():
            log.debug('new non-INVITE server transaction')
            return NonInviteServerTransaction(**kwargs)

        # It's only OK not to have a server transaction for a response
        # already when the response is a 2xx and the request type was an
        # INVITE, because RFC3261 says it is the TU's job to ensure 2xxs
        # are transmitted all the way through, and only then tidy up,
        # and the only way that can
        # happen is if the transaction is not responsible for its
        # transmission. This means the initial server INVITE transaction
        # is completed when the TU passes in the 2xx, and so cannot be
        # reused.
        #
        # In this case we return the special one-off transaction object,
        # which is not (should not be!) retained anywhere.
        if (200 <= msg.type < 300 and
                msg.cseqheader.reqtype == msg.types.INVITE):
            log.debug('INVITE 2xx re-transmission, make oneshot server trans')
            return OneShotServerTransaction(**kwargs)

        raise KeyError(
            'No server transaction could be found for %s message with request '
            'type %s' % (
                msg.type, msg.cseqheader.reqtype))
