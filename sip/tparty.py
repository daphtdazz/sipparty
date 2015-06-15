"""tparty.py

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
import socket

if __name__ == "__main__":
    logging.basicConfig()
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)

import sip
from sip import _util
import scenario
import sipscenarios

tks = scenario.TransitionKeys


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
        self._tp_sipPartyLogLevel = sip.party.log.level
        sip.party.log.setLevel(logging.DEBUG)
        sip.fsm.log.setLevel(logging.DEBUG)

    def tearDown(self):
        sip.party.log.setLevel(self._tp_sipPartyLogLevel)

    def testIncompleteParty(self):
        sipclient = sipscenarios.SimpleParty()
        tp = weakref.ref(sipclient._pt_transport)
        self.assertIsNotNone(tp())
        del sipclient
        _util.WaitFor(lambda: tp() is None, 2)
        self.assertIsNone(tp())

    def testBasicPartyTCP(self):
        self.subTestBasicParty(socket.SOCK_STREAM)

    def testBasicPartyUDP(self):
        self.subTestBasicParty(socket.SOCK_DGRAM)

    def subTestBasicParty(self, socketType):

        class SimpleParty(sip.party.Party):
            pass

        SimpleParty.SetScenario(sipscenarios.Simple)

        self.assertEqual(SimpleParty.Scenario.__name__, "SimplePartyScenario")
        log.info(SimpleParty.Scenario._fsm_definitionDictionary)
        self.assertTrue(
            'INVITE' in
            SimpleParty.Scenario._fsm_definitionDictionary[
                scenario.InitialStateKey],
            SimpleParty.Scenario._fsm_definitionDictionary[
                scenario.InitialStateKey])
        self.assertFalse(
            'invite' in
            SimpleParty.Scenario._fsm_definitionDictionary[
                scenario.InitialStateKey])
        p1 = SimpleParty(socketType=socketType)
        wp1 = weakref.ref(p1)

        log.warning("{ EXPECTING EXCEPTION UnexpectedState")
        p1.sendInvite()
        self.assertRaises(
            sip.party.UnexpectedState,
            lambda: wp1().waitUntilState(
                wp1().States.InCall,
                error_state=wp1().States.Initial))
        log.warning("} EXPECTING EXCEPTION UnexpectedState")
        p2 = SimpleParty(socketType=socketType)
        wp2 = weakref.ref(p2)
        p2.listen()
        p1.sendInvite(p2)

        _util.WaitFor(lambda: wp1().state == wp1().States.InCall, 1)
        _util.WaitFor(lambda: p2.state == p2.States.InCall, 1)

        p1tag = p1.myTag
        p2tag = p2.myTag
        self.assertIsNotNone(p1tag)
        self.assertIsNotNone(p2tag)
        self.assertEqual(p1tag, p2.theirTag)
        self.assertEqual(p2tag, p1.theirTag)

        p1.sendBye()

        _util.WaitFor(lambda: wp1().state == wp1().States.CallEnded, 1)
        _util.WaitFor(lambda: p2.state == p2.States.CallEnded, 1)

        self.assertEqual(p1tag, p1.myTag)
        self.assertEqual(p2tag, p1.theirTag)
        self.assertEqual(p1tag, p2.theirTag)
        self.assertEqual(p2tag, p2.myTag)

        wtp = weakref.ref(p1._pt_transport)
        del p1
        _util.WaitFor(lambda: wtp() is None, 1)

        # Test that we can re-use existing parties.
        p2.reset()
        p1 = SimpleParty(socketType=socketType)
        wp1 = weakref.ref(p1)
        p1.listen()
        p2.sendInvite(p1)
        _util.WaitFor(lambda: wp1().state == wp1().States.InCall, 1)
        _util.WaitFor(lambda: p2.state == p2.States.InCall, 1)

        p1.sendBye()

        _util.WaitFor(lambda: wp1().state == wp1().States.CallEnded, 1)
        _util.WaitFor(lambda: p2.state == p2.States.CallEnded, 1)

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

if __name__ == "__main__":
    unittest.main()
