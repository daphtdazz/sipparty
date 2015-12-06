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
import os
import re
import sys
import unittest
from .. import (sip, transport)
from ..fsm import (retrythread, fsm)
from ..sip import (siptransport, field)
from ..sip.components import AOR
from ..sip.siptransport import SIPTransport
from ..util import (abytes, WaitFor)
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestSIPTransport(SIPPartyTestCase):

    def setUp(self):
        # self.pushLogLevel('siptransport', logging.DETAIL)
        # self.pushLogLevel('transport', logging.DETAIL)

        self.def_hname_mock = MagicMock()
        self.def_hname_mock.return_value = 'localhost'
        self.hostname_patch = patch.object(
            transport, 'default_hostname', new=self.def_hname_mock)
        self.hostname_patch.start()

    def tearDown(self):

        self.hostname_patch.stop()
        super(TestSIPTransport, self).tearDown()

    def test_general_dgram(self):

        global rcvd_message
        rcvd_message = None

        def newDialogHandler(message):
            global rcvd_message
            rcvd_message = message
            log.debug("NewDialogHandler consumed the message.")

        log.info('Make SIPTransport object')
        tp = SIPTransport()
        tp1 = SIPTransport()
        self.assertIs(tp, tp1)

        tp.listen()

    def test_specific(self):
        laddr = tp.listen(name="127.0.0.1")

        log.info('Make INVITE message')
        msg = sip.Message.invite()
        msg.ToHeader.aor = b"alice@atlanta.com"
        msg.FromHeader.aor = b"bob@biloxi.com"
        msg.ContactHeader.field.value.uri.aor.host.address = abytes(laddr[0])
        msg.ContactHeader.field.value.uri.aor.host.port = laddr[1]

        log.info('Add Dialog Handler for our AOR')
        tp.addDialogHandlerForAOR(msg.ToHeader.aor, newDialogHandler)
        log.info('Send the message')
        tp.sendMessage(msg, laddr)

        log.info('Receive the message.')
        WaitFor(lambda: rcvd_message is not None, 1)
