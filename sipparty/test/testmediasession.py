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
from ..media.session import (MediaSession, NoMediaSessions, Session)
from ..sdp import SDPIncomplete
from ..sdp.sdpsyntax import (MediaTypes, AddrTypes, NetTypes)
from ..transport import ValidPortNum
from ..util import TestCaseREMixin
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestSession(SIPPartyTestCase):

    def test_basic_session(self):

        log.info("Create new Session and check it produces SDP when ready.")
        ms = Session(username=b"alice")
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.name = '127.0.0.1'
        self.assertEqual(ms.address, b'127.0.0.1')
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP4 127.0.0.1\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        ms.address = b"::1"
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 ::1\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

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
            b'o=alice \d+ \d+ IN IP6 ::1\r\n'
            b's= \r\n'
            b't=0 0\r\n'
            b'm=audio 11000 RTP/AVP 123\r\n$')

    def test_media_session_parent(self):
        ss = Session()
        ms = MediaSession()

        log.info('Show that we can\'t add a media session and create one.')
        self.assertRaises(
            TypeError, ss.addMediaSession, mediaSession=ms,
            mediaType=MediaTypes.audio)

        ss.name = 'atlanta.com'
        ss.addMediaSession(mediaSession=ms)
        self.assertEqual(ms.name, 'atlanta.com')

        log.info(
            'Demonstrate that a media session has a weak reference to its '
            'parent.')
        self.assertIs(ms.parent_session, ss)
        del ss
        self.assertIs(ms.parent_session, None)

    def test_on_demand_port_allocation(self):
        ss = Session(username=b'alice')

        log.info('Exception if no media sessions.')
        self.assertRaises(NoMediaSessions, ss.listen)

        log.info('Listening allocates us a port.')
        ss.addMediaSession(
            mediaType=MediaTypes.audio, transProto = b"RTP/AVP", fmts=[123])
        ss.listen()
        self.assertTrue(ValidPortNum(ss.mediaSession.port))
        self.assertMatchesPattern(
            ss.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP4 127.0.0.1\r\n'
            b's= \r\n'
            b't=0 0\r\n'
            b'm=audio %(port)d RTP/AVP 123\r\n'
            b'c=IN IP4 127.0.0.1\r\n' % {
                b'port': ss.mediaSession.port
            }
        )

        log.info(
            'Test that listen works even when the IP addr type must be '
            'deduced')
        ss = Session(username=b'bob', name='127.0.0.1')
        ss.addMediaSession(
            mediaType=MediaTypes.audio, transProto = b"RTP/AVP", fmts=[123])

    def test_domain_names(self):
        log.info('Check that we can create a session at a domain name.')
        ms = Session()
        ms.username = b'alice'
        ms.address = b'atlanta.com'
        # Incomplete because with a domain name we must also specify the IP
        # address type.
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.addressType = AddrTypes.IP6
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 atlanta.com\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        log.info('We can change the domain name without changing the IP type.')
        ms.address = b'biloxi.com'
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 biloxi.com\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        log.info('We can set both still.')
        ms.address = b'1.2.3.4'
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP4 1.2.3.4\r\n'
            b's= \r\n'
            b't=0 0\r\n$')
