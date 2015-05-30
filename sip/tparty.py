"""tpart.py

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
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
import unittest

import sip
from sip import _util
import scenario
import sipscenarios

log = logging.getLogger()
tks = scenario.TransitionKeys


class TestParty(unittest.TestCase):

    def testIncompleteParty(self):
        sipclient = sipscenarios.SimpleParty()
        tp = weakref.ref(sipclient._pt_transport)
        self.assertIsNotNone(tp())
        del sipclient
        _util.WaitFor(lambda: tp() is None, 2)
        self.assertIsNone(tp())

    def testBasicParty(self):

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
        p1 = SimpleParty()
        p1.sendInvite()
        self.assertRaises(
            sip.party.UnexpectedState,
            lambda: p1.waitUntilState(
                p1.States.InCall,
                error_state=p1.States.Initial))
        p2 = SimpleParty()
        p2._pt_transport.listen()
        p1.sendInvite(p2)

        _util.WaitFor(lambda: p1.state == p1.States.InCall, 1)
        _util.WaitFor(lambda: p2.state == p2.States.InCall, 1)

        self.assertIsNotNone(p1.myTag)
        self.assertIsNotNone(p1.theirTag)
        self.assertEqual(p1.myTag, p2.theirTag)
        self.assertEqual(p1.theirTag, p2.myTag)

        p1.sendBye()

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
