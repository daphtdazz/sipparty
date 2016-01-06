"""testparty.py

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
import logging
from socket import SOCK_STREAM, SOCK_DGRAM
import unittest
import weakref
from ..media.sessions import SingleRTPSession
from ..party import (Party)
from ..parties import (NoMediaSimpleCallsParty)
from ..sip.dialogs import SimpleCall
from ..sip.siptransport import SIPTransport
from ..transport import NameLoopbackAddress
from ..util import (abytes, WaitFor)
from .setup import SIPPartyTestCase

log = logging.getLogger()


class TestParty(SIPPartyTestCase):

    def assertIsNotNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), 'assertIsNotNone'):
            return super(TestParty, self).assertIsNotNone(exp, *args, **kwargs)

        return self.assertTrue(exp is not None)

    def assertIsNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), 'assertIsNone'):
            return super(TestParty, self).assertIsNone(exp, *args, **kwargs)

        return self.assertTrue(exp is None)

    def setUp(self):
        self.tp = SIPTransport()

    def tearDown(self):
        del self.tp

    def testBasicPartyTCP(self):
        self.skipTest('TCP not yet implemented')
        self.subTestBasicParty(SOCK_STREAM, )

    def testBasicPartyUDPIPv4(self):
        self.pushLogLevel('party', logging.DEBUG)
        self.subTestBasicParty(SOCK_DGRAM, '127.0.0.1')

    def testBasicPartyUDPIPv6(self):
        self.subTestBasicParty(SOCK_DGRAM, '::1')

    def subTestBasicParty(self, sock_type, contact_name):

        # self.pushLogLevel('transport', logging.DEBUG)
        # self.pushLogLevel('party', logging.DEBUG)
        # self.pushLogLevel('dialog', logging.DEBUG)

        assert sock_type == SOCK_DGRAM

        log.info('Listen with type %r', sock_type)

        BasicParty = type(
            'BasicParty', (Party,), {
                'InviteDialog': SimpleCall,
                'MediaSession': type(
                    'LoopbackSingleRTPSession', (SingleRTPSession,), {
                        'DefaultName': NameLoopbackAddress
                    }
                )
            }
        )

        log.info('Start p1')
        p1 = BasicParty(aor=b'alice@atlanta.com')
        log.info('..and p2')
        p2 = BasicParty(aor=b'bob@biloxi.com')

        log.info('p1 listens')
        self.pushLogLevel('transport', logging.DEBUG)
        p1.listen(name=contact_name, sock_type=sock_type)

        log.info('p2 invites p1')
        invD = p2.invite(p1)

        WaitFor(lambda: invD.state == invD.States.InDialog, 1)

        self.assertEqual(len(p1.inCallDialogs), 1)
        self.assertEqual(len(p2.inCallDialogs), 1)

        log.info('p1 terminates')
        invD.terminate()
        WaitFor(lambda: invD.state == invD.States.Terminated, 1)

        # Try another call.
        p3 = BasicParty(
            aor=b'charlie@charlesville.com',
            contactURI__address=abytes(contact_name))
        p3.listen(sock_type=sock_type, name=contact_name, port=5061)
        self.assertTrue(p3.transport is p1.transport)
        self.assertTrue(p3.transport is p2.transport)
        invD3to2 = p2.invite(p3)

        WaitFor(lambda: invD3to2.state == invD3to2.States.InDialog, 1)

        self.assertEqual(len(p3.inCallDialogs), 1)
        self.assertEqual(len(p2.inCallDialogs), 1)
        self.assertEqual(len(p1.inCallDialogs), 0)

        invD3to2.terminate()
        WaitFor(lambda: invD3to2.state == invD3to2.States.Terminated, 1)

        self.assertEqual(len(p3.inCallDialogs), 0)
        self.assertEqual(len(p2.inCallDialogs), 0)
        self.assertEqual(len(p1.inCallDialogs), 0)

        return

    def test_no_media_party(self):

        log.info('Create two new no-media parties.')
        p1 = NoMediaSimpleCallsParty()
        p2 = NoMediaSimpleCallsParty()

        p1.listen()
        self.assertEqual(p1.listenAddress, ())
