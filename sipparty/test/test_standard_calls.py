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
from __future__ import absolute_import

import logging
import os
import threading
from timeit import default_timer

from ..parse import Parser
from ..parties import NoMediaSimpleCallsParty
from ..sip.siptransport import SIPTransport
from ..sip.standardtimers import StandardTimers
from ..util import WaitFor

from .base import SIPPartyTestCase

log = logging.getLogger(__name__)


class TDialogDelegate:

    def __init__(self):
        self.invite_count = 0
        self.dialog = None

    def fsm_dele_handle_invite(self, dialog, *args, **kwargs):
        self.dialog = dialog
        self.invite_count += 1


class TestStandardDialog(SIPPartyTestCase):

    def setUp(self):
        super(TestStandardDialog, self).setUp()
        self.patch_clock()

    def test_retransmit(self):
        log.info('test_retransmit')
        tp = SIPTransport()
        assert tp.connected_socket_count == 0
        assert tp.listen_socket_count == 0
        dd = TDialogDelegate()

        p1, p2 = [
            NoMediaSimpleCallsParty(dialog_delegate=dd) for ii in range(2)]

        p1.display_name_uri = 'sip:alice@atlanta.com'
        p2.display_name_uri = 'sip:bob@biloxi.com'

        p2.listen(port=0)

        p1.invite(p2)
        WaitFor(lambda: dd.invite_count == 1)

        log.info('Get the client transaction')
        self.assertIsNotNone(dd.dialog)
        rq = dd.dialog.request
        self.assertIsNotNone(rq)
        tm = tp.transaction_manager
        ctrns = tm.transaction_for_outbound_message(dd.dialog.request)
        tm.transaction_for_inbound_message(dd.dialog.request)
        self.assertEqual(ctrns.state, ctrns.States.calling)
        self.assertEqual(ctrns.retransmit_count, 0)

        log.info('Trigger a retransmit')
        self.clock_time = StandardTimers.T1
        ctrns.checkTimers()
        self.assertEqual(ctrns.retransmit_count, 1)

    def test_multiple_calls(self):
        Parser.PROFILE = True
        self.addCleanup(
            lambda:
                log.info(Parser.stats_summary()) and
                setattr(Parser, 'PROFILE', False))

        start = default_timer()
        log.info('Create parties which will listen')
        nn = int(os.environ.get('SPT_NN', 10))
        parties = [
            NoMediaSimpleCallsParty(aor='callee-%d@listen.com' % (test + 1,))
            for test in range(nn)]

        log.info('Listen parties')
        list(map(lambda x: x.listen(port=0), parties))

        # The transport is implemented using sipparty.util.Singleton which
        # provides a powerful and simple Singleton design pattern
        # implementation.
        log.info('Check listen socket count')
        tp = SIPTransport()
        self.assertEqual(tp.listen_socket_count, 1)

        log.info('Create send parties')
        send_parties = [
            NoMediaSimpleCallsParty(aor='caller-%d@send.com' % (test + 1,))
            for test in range(nn)
        ]
        log.info('Start dialogs')
        dlgs = list(
            cl.invite(cle) for cl, cle in zip(send_parties, parties))

        for dlg in dlgs:
            dlg.waitForStateCondition(lambda st: st == dlg.States.InDialog)

        log.info('There are %d threads active' % (threading.active_count(),))

        log.info('Terminate dialogs')
        for dlg in dlgs:
            dlg.terminate()

        for dlg in dlgs:
            dlg.waitForStateCondition(lambda st: st == dlg.States.Terminated)

        stop = default_timer()
        log.info('From start to finish took %f seconds', stop - start)
