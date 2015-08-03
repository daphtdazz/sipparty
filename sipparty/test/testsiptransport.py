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
import sys
import os
import re
import time
import timeit
import logging
import unittest
import six

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)

from sipparty import util, sip
from sipparty.fsm import retrythread, fsm
from sipparty.sip import transport, siptransport, field
from sipparty.sip.components import AOR
SIPTransport = siptransport.SIPTransport


class TestSIPTransport(unittest.TestCase):

    def setUp(self):
        self.transLL = transport.log.level
        transport.log.setLevel(logging.DEBUG)
        self.sipTransLL = siptransport.log.level
        siptransport.log.setLevel(logging.DEBUG)

    def tearDown(self):
        transport.log.setLevel(self.transLL)
        siptransport.log.setLevel(self.sipTransLL)

    def testSIPTransport(self):

        global rcvd_message
        rcvd_message = None

        def newDialogHandler(message):
            global rcvd_message
            rcvd_message = message
            log.debug("NewDialogHandler consumed the message.")

        tp = SIPTransport()
        laddr = tp.listen()

        aliceAOR = AOR("alice", "atlanta.com")
        bobAOR = AOR("bob", "biloxi.com")
        msg = sip.Message.invite()
        msg.ToHeader.field.value.uri.aor = aliceAOR
        msg.FromHeader.field.value.uri.aor = bobAOR
        msg.ContactHeader.field.value.uri.aor.host.host = laddr[0]
        msg.ContactHeader.field.value.uri.aor.host.port = laddr[1]

        tp.addDialogHandlerForAOR(newDialogHandler, aliceAOR)
        tp.sendMessage(msg, laddr)

        util.WaitFor(lambda: rcvd_message is not None, 1)

if __name__ == "__main__":
    unittest.main()
