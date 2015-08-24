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
from setup import SIPPartyTestCase
from sipparty import (util, vb, sip)
from sipparty.sdp import SDPIncomplete
from sipparty.sdp.sdpsyntax import (MediaTypes, AddrTypes, NetTypes)
from sipparty.media import Session

log = logging.getLogger(__name__)


class TestSession(util.TestCaseREMixin, SIPPartyTestCase):

    def testBasicSession(self):

        log.info("Create new Session and check it produces SDP when ready.")
        ms = Session(username=b"alice")
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.address = b"127.0.0.1"
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            'o=alice \d+ \d+ IN IP4 127.0.0.1\r\n'
            's= \r\n'
            't=0 0\r\n$')

        ms.addMediaSession(mediaType=MediaTypes.audio)
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.mediaSession.port = 11000
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.mediaSession.transProto = b"RTP/AVP"
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.mediaSession.fmts = [123]
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            'o=alice \d+ \d+ IN IP4 127.0.0.1\r\n'
            's= \r\n'
            't=0 0\r\n'
            'm=audio 11000 RTP/AVP 123\r\n$')

if __name__ == "__main__":
    unittest.main()
