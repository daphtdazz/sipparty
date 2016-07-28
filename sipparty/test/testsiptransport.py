"""tsiptransport.py

Unit tests for the SIP transport.

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
from socket import (AF_INET, SOCK_DGRAM)
from .. import (sip, transport)
from ..sip.siptransport import AORHandler, SIPTransport
from ..util import WaitFor
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestSIPTransport(AORHandler, SIPPartyTestCase):

    def setUp(self):
        self.def_hname_mock = MagicMock()
        self.def_hname_mock.return_value = 'localhost'
        self.hostname_patch = patch.object(
            transport, 'default_hostname', new=self.def_hname_mock)
        self.hostname_patch.start()

    def tearDown(self):

        self.hostname_patch.stop()
        super(TestSIPTransport, self).tearDown()

    def new_dialog_from_request(self, message):
        self.rcvd_messages.append(message)
        log.debug("NewDialogHandler consumed the message.")

    def test_general(self):

        sock_family = AF_INET
        sock_type = SOCK_DGRAM

        self.rcvd_messages = []

        log.info('Make SIPTransport object')
        tp = SIPTransport()
        tp1 = SIPTransport()
        self.assertIs(tp, tp1)

        l_desc = tp.listen_for_me(sock_type=sock_type, sock_family=sock_family)

        log.info('Make INVITE message')
        msg = sip.Message.invite()
        msg.ToHeader.aor = b"alice@atlanta.com"
        msg.FromHeader.aor = b"bob@biloxi.com"
        msg.ContactHeader.field.value.uri.aor.host.address = b'127.0.0.1'
        msg.ContactHeader.field.value.uri.aor.host.port = l_desc.port

        log.info('Check add dialog handler requires an AOR')
        self.assertRaises(
            TypeError, tp.addDialogHandlerForAOR, 'bob@biloxi.com', self)

        log.info('Add Dialog Handler for our AOR')
        tp.addDialogHandlerForAOR(msg.ToHeader.aor, self)
        log.info('Send the message')
        tp.send_message_with_transaction(
            msg, remote_name='127.0.0.1', remote_port=l_desc.port)

        log.info('Receive the message.')
        WaitFor(lambda: len(self.rcvd_messages) > 0, 1)
        rmsg = self.rcvd_messages.pop()
        self.assertEqual(msg.type, rmsg.type, rmsg)
