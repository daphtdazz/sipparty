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
from threading import Semaphore
from time import sleep

from ..fsm import fsmtimer
from ..fsm import retrythread
from ..sip.message import Message
from ..sip.prot import (
    DefaultGiveupTimeMS, DefaultMaximumRetryTimeMS, DefaultRetryTimeMS)
from ..sip.siptransaction import (
    TransactionManager,
    TransactionTransport, TransactionUser, NonInviteClientTransaction)
from ..util import WaitFor
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TransactionTest(
        TransactionTransport, TransactionUser, SIPPartyTestCase):

    Clock = MagicMock()

    def setUp(self):
        self.retry = 0
        self.cleanup = 0

        self.Clock.return_value = 0
        sema = Semaphore(0)
        self.select_semaphore = sema
        self.msgs_sent = []
        self.msg_tu_datas = []

        def retry_thread_select(self, *args, **kwargs):
            log.debug('Wait for the select semaphore')
            sema.acquire()
            log.debug('select semaphore acquired')

            # small sleep to improve chance of garbage collection before the
            # semaphore is exhausted.
            sleep(0.0001)
            return [], [], []

        self.select_patch = patch.object(
            retrythread, 'select', new=retry_thread_select)
        self.select_patch.start()

    def tearDown(self):
        # Given the unpredicatibility of python object lifetimes we don't know
        # exactly when the retry threads will be garbage collected and stop, so
        # flood the semaphore to endeavour to make sure they don't deadlock on
        # it before being tidied.
        #
        # That's also why this inline function is used, so that we use separate
        # semaphores for each test.
        log.debug('Release semaphore for tearDown.')
        for ii in range(1000):
            self.select_semaphore.release()
        self.select_patch.stop()
        super(TransactionTest, self).tearDown()

    def sendMessage(self, msg, remote_name, remote_port):
        self.msgs_sent.append(msg)

    def consumeMessage(self, msg, tu_data=None):
        self.msg_tu_datas.append((msg, tu_data))


class TestNonInviteTransaction(TransactionTest):

    @patch.object(fsmtimer, 'Clock', new=TransactionTest.Clock)
    @patch.object(retrythread, 'Clock', new=TransactionTest.Clock)
    def test_basic(self):
        non_inv_trans = NonInviteClientTransaction(
            transaction_user=self, transport=self,
            remote_name='nowhere.com', remote_port=5060)
        non_inv_trans.hit('request', 'message')

        # Test that the standard timers work OK.
        self.assertEqual(DefaultRetryTimeMS, 500)
        self.assertEqual(DefaultMaximumRetryTimeMS, 4000)

        for time, resend_count in (
                (0, 1),
                (0.5, 2),
                (1.5, 3),
                (3.5, 4),
                (7.5, 5),
                (11.49, 5),
                (11.5, 6),
                (31.9, 7)):
            self.Clock.return_value = time
            log.debug('Release semaphore for resend')
            self.select_semaphore.release()
            WaitFor(lambda: len(self.msgs_sent) == resend_count)

        self.assertEqual(non_inv_trans.state, non_inv_trans.States.trying)
        self.Clock.return_value = 32
        WaitFor(lambda: non_inv_trans.state == non_inv_trans.States.terminated)


class TestTransactionManager(TransactionTest):

    def test_basic(self):
        tm = TransactionManager()
        tm2 = TransactionManager()
        self.assertIs(tm, tm2)

        invite = Message.invite()
        self.assertEqual(invite.CseqHeader.reqtype, 'INVITE')
        invite.ViaHeader.parameters.branch = b'branch1'

        inv_trns = tm.transaction_for_message(invite)
        self.assertIsNotNone(inv_trns)
        inv_trns2 = tm.transaction_for_message(invite)
        self.assertIs(inv_trns, inv_trns2)

        inv2 = Message.invite()
        invite.ViaHeader.parameters.branch = b'branch2'
        inv_trns2 = tm.transaction_for_message(inv2)
        self.assertIsNot(inv_trns2, inv_trns)
