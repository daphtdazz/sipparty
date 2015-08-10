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
import logging
import unittest
from six import binary_type as bytes
from sipparty import (sip, util, sdp)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)


class TestSDP(util.TestCaseREMixin, unittest.TestCase):

    def setUp(self):
        "Set up the TestSDP test case suite"
        self._sdpLogLevel = sdp.log.level
        sdp.log.setLevel(logging.DEBUG)

    def tearDown(self):
        util.log.setLevel(self._sdpLogLevel)

    def testSDP(self):

        sd = sdp.SessionDescription()
        self.assertRaises(sdp.SDPIncomplete, lambda: bytes(sd))
        sd.username = "alice"
        sd.addrType = sdp.AddrTypes.IP4
        sd.address = "atlanta.com"
        sd.addMediaDescription(
            mediaType=sdp.MediaTypes.audio, port=1815,
            proto="RTP/AVP", fmt=0)
        sd.mediaDescriptions[0].setConnectionDescription(
            addrType=sdp.AddrTypes.IP4,
            address="media.atlanta.com")

        data = bytes(sd)
        self.assertMatchesPattern(
            data,
            b"v=0\r\n"
            "o=alice \d+ \d+ IN IP4 atlanta.com\r\n"
            "s= \r\n"
            "t=0 0\r\n"
            "m=audio 1815 RTP/AVP 0\r\n"
            "c=IN IP4 media.atlanta.com\r\n"
            "\r\n"
        )

        # Parse.
        newDesc = sdp.SessionDescription.Parse(data)
        newData = bytes(newDesc)
        self.assertEqual(data, newData)
        # self.assertEqual(sd, newDesc)


if __name__ == "__main__":
    unittest.main()
