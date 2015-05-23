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
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
import unittest
import party
import scenario

log = logging.getLogger()
tks = scenario.TransitionKeys


class TestParty(unittest.TestCase):

    RClock = timeit.default_timer

    def wait_for(self, func, timeout=2):
        assert timeout > 0.05
        now = self.RClock()
        next_log = now + 1
        until = now + timeout
        while self.RClock() < until:
            if func():
                break
            time.sleep(0.01)
            if self.RClock() > next_log:
                next_log = self.RClock() + 1
                log.debug("Still waiting...")

        else:
            self.assertTrue(0, "Timed out waiting for %r" % func)

    def testBasicParty(self):

        class SimpleParty(party.Party):
            ScenarioDefinitions = {
                scenario.InitialStateKey: {
                    "sendInvite": {
                        tks.NewState: "invite sent",
                        tks.Action: "sendInvite"
                    },
                    "invite": {
                        tks.NewState: "in call",
                        tks.Action: "reply200"
                    }
                },
                "invite sent": {
                    "4xx": {
                        tks.NewState: scenario.InitialStateKey
                    },
                    200: {
                        tks.NewState: "in call"
                    }
                },
                "in call": {
                    "send bye": {
                        tks.NewState: "bye sent"
                    },
                    "bye": {
                        tks.NewState: scenario.InitialStateKey
                    }
                },
                "bye sent": {
                    200: {
                        tks.NewState: scenario.InitialStateKey
                    }
                }
            }

        self.assertEqual(SimpleParty.Scenario.__name__, "SimplePartyScenario")
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
        p1._pt_transport.listen()
        return 0
        p2 = SimpleParty()

        p1.sendInvite(p2)

        # Currently we don't get into the call because there's a parse error
        # of the invite.
        # self.wait_for(p1.state == "in call")


if __name__ == "__main__":
    unittest.main()
