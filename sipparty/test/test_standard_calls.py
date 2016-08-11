"""test_standard_calls.py

Unit tests for a SIP party.

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
from ..parties import NoMediaSimpleCallsParty
from ..sip.siptransport import SIPTransport
from ..sip.standardtimers import StandardTimers
from ..util import WaitFor

from .setup import patch, SIPPartyTestCase

log = logging.getLogger(__name__)


class TestDialogDelegate:

    def __init__(self):
        self.invite_count = 0
        self.dialog = None

    def fsm_dele_handle_invite(self, dialog, *args, **kwargs):
        self.dialog = dialog
        self.invite_count += 1


class TestStandardDialog(SIPPartyTestCase):

    def setUp(self):
        super(TestStandardDialog, self).setUp()
        pp = patch.object(fsmtimer, 'Clock', new=SIPPartyTestCase.Clock)
        pp.start()
        self.addCleanup(pp.stop)

    def test_retransmit(self):

        tp = SIPTransport()
        dd = TestDialogDelegate()

        p1, p2 = [
            NoMediaSimpleCallsParty(dialog_delegate=dd) for ii in range(2)]

        p1.display_name_uri = 'sip:alice@atlanta.com'
        p2.display_name_uri = 'sip:bob@biloxi.com'

        p2.listen(port=0)

        p1.invite(p2)
        WaitFor(lambda: dd.invite_count == 1)

        log.info('Get the client transaction')
        self.assertIsNotNone(dd.dialog)
        self.assertIsNotNone(dd.dialog.request)
        tm = tp.transaction_manager
        trns = tm.transaction_for_outbound_message(dd.dialog.request)
        self.assertEqual(trns.state, trns.States.calling)
        self.assertEqual(trns.retransmit_count, 0)

        log.info('Trigger a retransmit')
        self.Clock.return_value = StandardTimers.T1
        trns.checkTimers()
        self.assertEqual(trns.retransmit_count, 1)
