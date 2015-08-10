"""testparty.py

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
import sys
import os
import re
import timeit
import time
import logging
import weakref
import unittest
from socket import SOCK_STREAM, SOCK_DGRAM

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)

from sipparty import (fsm, sip, util, vb, deepclass, parse)
from sipparty.util import WaitFor
from sipparty.sip import components, dialog, transport, siptransport, party
from sipparty.sip.transport import Transport
from sipparty.sip.dialogs import SimpleCall

tks = sip.scenario.TransitionKeys


class TestParty(unittest.TestCase):

    def assertIsNotNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), "assertIsNotNone"):
            return super(TestParty, self).assertIsNotNone(exp, *args, **kwargs)

        return self.assertTrue(exp is not None)

    def assertIsNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), "assertIsNone"):
            return super(TestParty, self).assertIsNone(exp, *args, **kwargs)

        return self.assertTrue(exp is None)

    def setUp(self):
        #sip.party.log.setLevel(logging.DEBUG)
        #dialog.log.setLevel(logging.DEBUG)
        # fsm.fsm.log.setLevel(logging.DEBUG)
        # sip.message.log.setLevel(logging.DEBUG)
        # util.log.setLevel(logging.DEBUG)
        #vb.log.setLevel(logging.DEBUG)
        #deepclass.log.setLevel(logging.DETAIL)
        # fsm.retrythread.log.setLevel(logging.DEBUG)
        # parse.log.setLevel(logging.DEBUG)
        transport.log.setLevel(logging.DEBUG)
        #siptransport.log.setLevel(logging.DETAIL)
        pass

    def testBasicPartyTCP(self):
        self.skipTest("TCP not yet implemented")
        self.subTestBasicParty(SOCK_STREAM, )

    def testBasicPartyUDP(self):
        self.subTestBasicParty(SOCK_DGRAM, "127.0.0.1")

    def testBasicPartyUDPIPv6(self):
        self.subTestBasicParty(SOCK_DGRAM, "::1")

    def subTestBasicParty(self, socketType, contactAddress):

        BasicParty = type(
            "BasicParty", (sip.party.Party,),
            {"InviteDialog": SimpleCall})

        p1 = BasicParty(
            aor="alice@atlanta.com", contactURI_address=contactAddress,
            socketType=socketType)
        p2 = BasicParty(
            aor="bob@biloxi.com", contactURI_address=contactAddress,
            socketType=socketType)
        p1.listen()
        p2.listen()
        invD = p1.invite(p2)

        WaitFor(lambda: invD.state == invD.States.InDialog, 1)

        self.assertEqual(len(p1.inCallDialogs), 1)
        self.assertEqual(len(p2.inCallDialogs), 1)

        invD.terminate()
        WaitFor(lambda: invD.state == invD.States.Terminated, 1)

        # Try another call.
        p3 = BasicParty(
            aor="charlie@charlesville.com", contactURI_address=contactAddress,
            socketType=socketType)
        p3.listen()
        invD3to2 = p2.invite(p3)

        WaitFor(lambda: invD3to2.state == invD3to2.States.InDialog, 1)

        self.assertEqual(len(p3.inCallDialogs), 1)
        self.assertEqual(len(p2.inCallDialogs), 1)
        self.assertEqual(len(p1.inCallDialogs), 0)

        invD3to2.terminate()
        WaitFor(lambda: invD3to2.state == invD3to2.States.Terminated, 1)

        self.assertEqual(len(p3.inCallDialogs), 0)
        self.assertEqual(len(p2.inCallDialogs), 0)
        self.assertEqual(len(p1.inCallDialogs), 0)

        return

    def testDudParty(self):

        self.assertRaises(
            KeyError,
            lambda: type("TestParty", (sip.party.Party,), {}).SetScenario({
                "state": {
                    "input": {
                        tks.NewState: "not declared!"
                    }
                }
            }))
        for bad_input in ("waitUntilState", "_sendInvite"):
            self.assertRaises(
                KeyError,
                lambda: type("TestParty", (sip.party.Party,), {}).SetScenario({
                    "first_state": {
                        bad_input: {
                            tks.NewState: "first_state"
                        }
                    }
                }))

    def testBasicSIPP(self):
        p1 = sipscenarios.SimpleParty(socketType=SOCK_DGRAM)

        data = bytearray()

        def byteConsumer(bytes):
            log.info("Consume %d bytes", len(bytes))
            data.extend(bytes)
            return len(bytes)

        p2transport = sip.transport.Transport(socketType=SOCK_DGRAM)
        p2transport.byteConsumer = byteConsumer
        p2transport.listen("127.0.0.1", 5060)
        p1.sendInvite("sippuser@127.0.0.1")

        WaitFor(lambda: len(data) > 0, 0.1)

        p2transport.send(
            b"SIP/2.0 180 Ringing\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1;branch={branch}\r\n"
            "From: <sip:alice@atlanta.com>;tag={taga}\r\n"
            "To: <sip:user@raspbmc.local>;tag=11586SIPpTag0116\r\n"
            "Call-ID: {call_id}\r\n"
            "CSeq: 1070250068 INVITE\r\n"
            "Contact: <sip:[::1]:5060;transport=UDP>\r\n"
            "Content-Length: 0\r\n\r\n".format(
                branch=p1, taga="", call_id=""))
        p2transport.send(
            )

if __name__ == "__main__":
    unittest.main()
