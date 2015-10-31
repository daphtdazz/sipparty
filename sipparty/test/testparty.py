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
from setup import SIPPartyTestCase
from sipparty import (fsm, sip, util, vb, deepclass, parse, Party)
from sipparty.util import WaitFor
from sipparty.sip import components, dialog
from sipparty.sip.dialogs import SimpleCall
from sipparty.media.sessions import SingleRTPSession

log = logging.getLogger()


class TestParty(SIPPartyTestCase):

    def assertIsNotNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), "assertIsNotNone"):
            return super(TestParty, self).assertIsNotNone(exp, *args, **kwargs)

        return self.assertTrue(exp is not None)

    def assertIsNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), "assertIsNone"):
            return super(TestParty, self).assertIsNone(exp, *args, **kwargs)

        return self.assertTrue(exp is None)

    def testBasicPartyTCP(self):
        self.skipTest("TCP not yet implemented")
        self.subTestBasicParty(SOCK_STREAM, )

    def testBasicPartyUDP(self):
        # self.pushLogLevel("party", logging.DEBUG)
        self.subTestBasicParty(SOCK_DGRAM, "127.0.0.1")

    def testBasicPartyUDPIPv6(self):
        self.subTestBasicParty(SOCK_DGRAM, "::1")

    def subTestBasicParty(self, socketType, contactAddress):

        assert socketType == SOCK_DGRAM

        BasicParty = type(
            "BasicParty", (Party,),
            {"InviteDialog": SimpleCall,
             "MediaSession": SingleRTPSession})

        p1 = BasicParty(
            aor="alice@atlanta.com", contactURI_address=contactAddress)
        p2 = BasicParty(
            aor="bob@biloxi.com", contactURI_address=contactAddress)
        p1.listen()
        p2.listen()
        self.assertTrue(p1.transport is p2.transport)
        invD = p1.invite(p2)

        WaitFor(lambda: invD.state == invD.States.InDialog, 1)

        self.assertEqual(len(p1.inCallDialogs), 1)
        self.assertEqual(len(p2.inCallDialogs), 1)

        invD.terminate()
        WaitFor(lambda: invD.state == invD.States.Terminated, 1)

        # Try another call.
        p3 = BasicParty(
            aor="charlie@charlesville.com", contactURI_address=contactAddress)
        p3.listen()
        self.assertTrue(p3.transport is p1.transport)
        self.assertTrue(p3.transport is p2.transport)
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

if __name__ == "__main__":
    unittest.main()
