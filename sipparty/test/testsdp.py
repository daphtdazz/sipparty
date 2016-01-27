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
from six import (binary_type as bytes)
from ..sdp import (
    AddrTypes, LineTypes, MediaTypes, SessionDescription, SDPIncomplete)
from ..util import (TestCaseREMixin)
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestSDP(SIPPartyTestCase):

    def setUp(self):
        # self.pushLogLevel('sdp.sdp', logging.DEBUG)
        # self.pushLogLevel('testsdp', logging.DEBUG)
        pass

    def testSDPLine(self):
        for args, byte_res in (
                    ((LineTypes.v, 0), b'v=0'),
                    ((LineTypes.s, b'asdf'), b's=asdf')
                ):
            log.info('Check Line%r == %r', args, byte_res)
            self.assertEqual(SessionDescription.Line(*args), byte_res)

    def testSDP(self):

        sd = SessionDescription()
        self.assertRaises(SDPIncomplete, lambda: bytes(sd))
        sd.username = b"alice"
        sd.address = b"atlanta.com"
        sd.addressType = AddrTypes.IP4
        sd.addMediaDescription(
            mediaType=MediaTypes.audio, port=1815,
            transProto=b"RTP/AVP", formats=[0])
        sd.mediaDescriptions[0].address = b"media.atlanta.com"
        sd.mediaDescriptions[0].addressType = AddrTypes.IP4

        log.info('Check bytes of sd')
        log.debug('SD is %r', sd)
        data = bytes(sd)
        self.assertMatchesPattern(
            data,
            b"v=0\r\n"
            b"o=alice \d+ \d+ IN IP4 atlanta.com\r\n"
            b"s= \r\n"
            b"t=0 0\r\n"
            b"m=audio 1815 RTP/AVP 0\r\n"
            b"c=IN IP4 media.atlanta.com\r\n$"
        )

        # Parse.
        log.info('Check Parse of data')
        log.debug('Data to parse: %r', data)
        newDesc = SessionDescription.Parse(data)
        newData = bytes(newDesc)
        self.assertEqual(data, newData)
