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
from socket import AF_INET6
from ..media.session import (MediaSession, NoMediaSessions, Session)
from ..sdp import SDPIncomplete
from ..sdp.sdpsyntax import (
    AddrTypes, AddressToSDPAddrType, MediaTypes, NetTypes)
from ..transport import (
    IPAddressFamilyFromName, IsValidPortNum, SOCK_FAMILIES)
from ..util import (abytes, TestCaseREMixin, WaitFor, WeakProperty)
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestSession(SIPPartyTestCase):

    def test_basic_session(self):

        self.pushLogLevel('adapter', logging.DEBUG)
        log.info("Create new Session and check it produces SDP when ready.")
        sess = Session(username=b"alice")
        self.assertRaises(SDPIncomplete, sess.sdp)
        sess.address = '127.0.0.1'
        str(sess.description)

        self.assertMatchesPattern(
            sess.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP4 127.0.0.1\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        sess.address = "::1"
        self.assertMatchesPattern(
            sess.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 ::1\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        sess.addMediaSession(media_type=MediaTypes.audio)
        self.assertEqual(len(sess.description.mediaDescriptions), 1)
        msess = sess.mediaSession
        mdesc = sess.description.mediaDescriptions[0]
        self.assertIs(msess, mdesc._adapted_object())

        msess.port = 11000
        self.assertEqual(msess.port, 11000)
        self.assertEqual(msess.port, mdesc.port)
        self.assertRaises(SDPIncomplete, lambda: sess.sdp())

        sess.mediaSession.transProto = "RTP/AVP"
        self.assertRaises(SDPIncomplete, lambda: sess.sdp())

        sess.mediaSession.formats = {123: {}}
        self.assertMatchesPattern(
            sess.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 ::1\r\n'
            b's= \r\n'
            b't=0 0\r\n'
            b'm=audio 11000 RTP/AVP 123\r\n$')

    def test_media_session_parent(self):

        ss = Session()
        ms = MediaSession()

        log.info('Show that we can\'t add a media session and create one.')
        with self.assertRaises(TypeError):
            ss.addMediaSession(mediaSession=ms, mediaType=MediaTypes.audio)

        ss.addMediaSession(ms)
        log.info(
            'Demonstrate that a media session has a weak reference to its '
            'parent.')
        self.assertIs(ms.parent_session, ss)
        del ss
        WaitFor(lambda: ms.parent_session is None)
        self.assertIs(ms.parent_session, None)

    def test_on_demand_port_allocation(self):
        ss = Session(username=b'alice')

        log.info('Exception if no media sessions.')
        self.assertRaises(NoMediaSessions, ss.listen)

        log.info('Listening allocates us a port.')
        ss.addMediaSession(
            media_type=MediaTypes.audio, transProto = "RTP/AVP",
            formats={123: {}})
        ms = ss.mediaSession
        self.assertIsNone(ms.name)
        ss.listen()
        self.assertIsNotNone(ms.name)
        self.assertIn(IPAddressFamilyFromName(ms.name), SOCK_FAMILIES)
        self.assertTrue(IsValidPortNum(ms.port))
        self.assertMatchesPattern(
            ss.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN %(family)s %(address)s\r\n'
            b's= \r\n'
            b't=0 0\r\n'
            b'm=audio %(port)d RTP/AVP 123\r\n'
            b'c=IN %(family)s %(address)s\r\n' % {
                b'port': ss.mediaSession.port,
                b'family': AddressToSDPAddrType(abytes(ss.mediaSession.name)),
                b'address': abytes(ss.mediaSession.name)
            }
        )

    def test_domain_names(self):
        log.info('Check that we can create a session at a domain name.')
        ms = Session()
        ms.username = 'alice'
        ms.address = 'atlanta.com'
        # Incomplete because with a domain name we must also specify the IP
        # address type.
        self.assertRaises(SDPIncomplete, lambda: ms.sdp())
        ms.sock_family = AF_INET6
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 atlanta.com\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        log.info('We can change the domain name without changing the IP type.')
        ms.address = 'biloxi.com'
        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP6 biloxi.com\r\n'
            b's= \r\n'
            b't=0 0\r\n$')

        log.info('We can set both still.')
        self.pushLogLevel('vb', logging.DEBUG)
        ms.address = '1.2.3.4'
        ms.sock_family = None

        self.assertMatchesPattern(
            ms.sdp(),
            b'v=0\r\n'
            b'o=alice \d+ \d+ IN IP4 1.2.3.4\r\n'
            b's= \r\n'
            b't=0 0\r\n$')
