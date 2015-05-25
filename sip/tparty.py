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
import party
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
        p2 = SimpleParty()
        p2._pt_transport.listen()
        p1.hit("sendInvite", p2)

        _util.WaitFor(lambda: p1.state == "in call", 1)
        _util.WaitFor(lambda: p2.state == "in call", 1)

if __name__ == "__main__":
    unittest.main()
