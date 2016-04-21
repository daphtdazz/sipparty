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

from ..fsm import fsmtimer
from ..fsm import retrythread
from ..sip.prot import (
    DefaultGiveupTimeMS, DefaultMaximumRetryTimeMS, DefaultRetryTimeMS)
from ..sip.siptransaction import (
    TransactionTransport, TransactionUser, NonInviteClientTransaction)
from ..util import WaitFor
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestNonInviteTransaction(
        TransactionTransport, TransactionUser, SIPPartyTestCase):

    Clock = MagicMock()

    def setUp(self):
        self.retry = 0
        self.cleanup = 0

        self.Clock.return_value = 0
        self.select_semaphore = Semaphore(0)
        self.msgs_sent = []
        self.msg_tu_datas = []

        self.select_patch = patch.object(
            retrythread, 'select', new=self.retry_thread_select)
        self.select_patch.start()

    def tearDown(self):
        self.select_semaphore.release()
        self.select_patch.stop()
        super(TestNonInviteTransaction, self).tearDown()

    def retry_thread_select(self, *args, **kwargs):
        log.debug('Wait for the select semaphore')
        self.select_semaphore.acquire()
        log.debug('select semaphore acquired')
        return [], [], []

    def sendMessage(self, msg, remote_name, remote_port):
        self.msgs_sent.append(msg)

    def consumeMessage(self, msg, tu_data=None):
        self.msg_tu_datas.append((msg, tu_data))

    @patch.object(fsmtimer, 'Clock', new=Clock)
    @patch.object(retrythread, 'Clock', new=Clock)
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
            self.select_semaphore.release()
            WaitFor(lambda: len(self.msgs_sent) == resend_count)

        self.assertEqual(non_inv_trans.state, non_inv_trans.States.trying)
        self.Clock.return_value = 32
        self.select_semaphore.release()
        WaitFor(lambda: non_inv_trans.state == non_inv_trans.States.terminated)
