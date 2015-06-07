"""tsdp.py

Unit tests for the Session Description Protocol.

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
import six
import logging
import unittest

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)
bytes = six.binary_type

import sip


class TestSDP(sip._util.TestCaseREMixin, unittest.TestCase):

    def setUp(self):
        "Set up the TestSDP test case suite"

    def tearDown(self):
        pass

    def testSDP(self):

        sd = sip.SessionDescription()
        self.assertRaises(sip.sdp.SDPIncomplete, lambda: bytes(sd))
        sd.username = "alice"
        sd.addrType = sip.sdp.AddrTypes.IP4
        sd.address = "atlanta.com"

        self.assertMatchesPattern(
            bytes(sd),
            b"v=0\r\n"
            "o=alice \d+ \d+ IN IP4 atlanta.com\r\n"
            "s= \r\n"
            "\r\n"
        )

        return

        # Minimal and currently ungodly SDP.
        sdpdata = (
            b"v=0\r\n"
            "o=asdf\r\n"
            "s=fadsf\r\n"
            "t=asdf\r\n"
            "a=attr1\r\n"
            "a=attr2\r\n"
        )

        sdp = sip.sdp.SDP.Parse(sdpdata)
        self.assertEqual(bytes(sdp), sdpdata)
        # !!! self.assertEqual(sdp.version, 0)

if __name__ == "__main__":
    unittest.main()
