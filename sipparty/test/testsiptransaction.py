"""testsiptransaction.py

Unit tests for the SIP transaction FSM.

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
import logging

from ..fsm import fsmtimer
from ..fsm import retrythread
from ..sip.message import Message, MessageResponse
from ..sip.transaction import (
    Transaction, TransactionManager, TransactionTransport, TransactionUser)
from ..sip.transaction.client import NonInviteClientTransaction
from ..sip.transaction.server import InviteServerTransaction
from ..util import WaitFor
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TransactionTest(SIPPartyTestCase):

    Clock = MagicMock()

    def setUp(self):
        self.retry = 0
        self.cleanup = 0

        self.Clock.return_value = 0
        self.msgs_sent = []
        self.msg_tu_datas = []

        def retry_thread_select(in_, out, error, wait):
            assert wait >= 0

            return [], [], []

        select_patch = patch.object(
            retrythread, 'select', new=retry_thread_select)
        select_patch.start()
        self.addCleanup(select_patch.stop)

        # TU interface
        self.consume_request = MagicMock()
        self.consume_response = MagicMock()
        self.transport_error = MagicMock()
        self.timeout = MagicMock()
        self.transaction_terminated = MagicMock()

        # Transport Interface.
        self.send_message = MagicMock()

TransactionUser.register(TransactionTest)
TransactionTransport.register(TransactionTest)


class TestNonInviteTransaction(TransactionTest):

    @patch.object(fsmtimer, 'Clock', new=TransactionTest.Clock)
    @patch.object(retrythread, 'Clock', new=TransactionTest.Clock)
    def test_basic(self):

        class FakeMessage(object):
            type = 'FAKE'

            def __bytes__(self):
                return b'FAKE MESSAGE'

        non_inv_trans = NonInviteClientTransaction(
            transaction_user=self, transport=self,
            remote_name='nowhere.com', remote_port=5060)
        fm = FakeMessage()
        non_inv_trans.hit('request', fm)
        self.send_message.assert_called_with(fm, 'nowhere.com', 5060)
        self.assertEqual(self.send_message.call_count, 1)

        for time, resend_count in (
                (0.5, 2),
                (1.5, 3),
                (3.5, 4),
                (7.5, 5),
                (11.49, 5),
                (11.5, 6),
                (31.9, 11)):
            self.Clock.return_value = time
            WaitFor(lambda: self.send_message.call_count == resend_count)
            self.send_message.assert_called_with(fm, 'nowhere.com', 5060)

        self.assertEqual(non_inv_trans.state, non_inv_trans.States.trying)
        self.Clock.return_value = 32
        WaitFor(lambda: non_inv_trans.state == non_inv_trans.States.terminated)
        self.assertEqual(self.send_message.call_count, resend_count)


class TestTransactionManager(TransactionTest):

    def test_client_transaction(self):

        tm = TransactionManager(self)

        log.info('First invite')
        invite = Message.invite()
        self.assertEqual(invite.CseqHeader.reqtype, 'INVITE')
        self.assertRaises(
            ValueError, tm.transaction_for_outbound_message, invite)
        invite.ViaHeader.parameters.branch = b'branch1'

        inv_trns = tm.transaction_for_outbound_message(invite)
        self.assertIsNotNone(inv_trns)
        self.assertEqual(inv_trns.type, Transaction.types.client)
        inv_trns2 = tm.transaction_for_outbound_message(invite)
        self.assertIs(inv_trns, inv_trns2)

        log.info('Second invite')
        inv2 = Message.invite()
        inv2.ViaHeader.parameters.branch = b'branch2'
        inv_trns2 = tm.transaction_for_outbound_message(inv2)
        self.assertIsNot(inv_trns2, inv_trns)

        log.info('Get the transaction from a response')
        resp = MessageResponse(200)
        resp.CseqHeader = invite.CseqHeader
        resp.ViaHeader = invite.ViaHeader
        self.assertIs(tm.transaction_for_inbound_message(resp), inv_trns)

        log.info(
            'Show we get a server transaction if we pretend the first message '
            'was inbound')
        server_trns = tm.transaction_for_inbound_message(invite)
        self.assertIsNot(server_trns, inv_trns)
        self.assertEqual(server_trns.type, Transaction.types.server)

        log.info(
            'And that we get the same transaction if we attempt to send the '
            'same response')
        server_trns2 = tm.transaction_for_outbound_message(resp)
        self.assertIs(server_trns, server_trns2)


class TestServerTransaction(TransactionTest):

    def test_response_deduction(self):

        class ServerDelegate:

            def __init__(self):
                self.request_count = 0
                self.response_type = ''

            def fsm_dele_inform_tu(self, trans, action, obj):
                if action == 'consume_request':
                    self.request_count += 1
                    trans.hit('respond_' + self.response_type)

        # This is cheating, but saves implementing all the methods.
        # TransactionUser.register(ServerDelegate)

        sd = ServerDelegate()
        tp = MagicMock()
        TransactionTransport.register(MagicMock)
        tr = InviteServerTransaction(delegate=sd, transport=tp)

        inv = Message.invite()
        inv.ViaHeader.parameters.branch = b'branch'
        sd.response_type = 'notaresponse'
        self.assertRaises(ValueError, tr.hit, 'request', inv)
        self.assertEqual(sd.request_count, 1)
        self.assertEqual(tr.state, 'proceeding')

        log.info('Check we pick up the explicit input for 100')
        tr.hit('respond_100', inv)
        self.assertEqual(tr.state, 'proceeding')

        log.info('Check we pick up the general input for XXX')
        tr.hit('respond_400', inv)
        self.assertEqual(tr.state, 'completed')
