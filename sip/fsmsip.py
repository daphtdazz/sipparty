"""fsmsip.py

This module provides FSM states and inputs for SIP.

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
import prot
import request
import fsm
import _util

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

inputs = _util.Enum(
    list(request.Request.types) + prot.ResponseCodeMessages.keys(),
    normalize=lambda x: x.upper())

states = _util.Enum(
    ("no_dialogue", "starting_dialogue", "in_dialogue",
     "terminating_dialogue")
    )


class SimpleCallFSM(fsm.FSM):

    def __init__(self, *args, **kwargs):
        super(SimpleCallFSM, self).__init__(self, *args, **kwargs)

        # !!! Test out the FSM mechanism and try building a simple call fsm
        # with a view to determing what functions should go into a general
        # abstract SIP FSM class.
        #
        # !!!
        self.addTransition(states.no_dialogue, inputs.invite,
                           states.starting_dialogue)

    def receiveMessage(self, sipmessage):
        "Generate input based on the message."
        assert 0
        self.hit(sipmessage.startline)

#
# Unittest code follows.
#
import unittest


class TestFSMSIP(unittest.TestCase):

    def testSimpleCallFSM(self):
        scf = SimpleCallFSM()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
