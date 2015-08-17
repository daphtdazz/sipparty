"""testmediasession.py

Test the media session.

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
from six import (binary_type as bytes)
import unittest
from sipparty import (util, vb, sip)
from sipparty.sip import Session
from sipparty.sip import mediasession
from sipparty.sdp import SDPIncomplete

log = logging.getLogger(__name__)


class TestSession(util.TestCaseREMixin, unittest.TestCase):

    def testBasicSession(self):

        ms = Session(username="alice")
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())



if __name__ == "__main__":
    unittest.main()
