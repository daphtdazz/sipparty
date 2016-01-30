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
import gc
import logging
from socket import SOCK_STREAM, SOCK_DGRAM
from weakref import ref
from ..media.sessions import SingleRTPSession
from ..party import (Party)
from ..parties import (NoMediaSimpleCallsParty)
from ..sip.dialogs import SimpleCall
from ..sip.prot import Incomplete
from ..sip.siptransport import SIPTransport
from ..transport import (IsValidPortNum, NameLoopbackAddress)
from ..util import (abytes, WaitFor)
from .setup import SIPPartyTestCase

log = logging.getLogger()
log.setLevel(logging.INFO)


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
        self.wtp = ref(self.tp)

    def tearDown(self):
        log.info('Delete transport')
        del self.tp
        WaitFor(lambda: gc.collect() == 0 and self.wtp() is None, 2)
        log.info('Transport deleted')

    def testBasicPartyTCP(self):
        self.skipTest('TCP not yet implemented')
        self.subTestBasicParty(SOCK_STREAM, )

    def testBasicPartyUDPIPv4(self):
        self.subTestBasicParty(SOCK_DGRAM, '127.0.0.1')

    def testBasicPartyUDPIPv6(self):
        self.subTestBasicParty(SOCK_DGRAM, '::1')

    def subTestBasicParty(self, sock_type, contact_name):

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

        p1.listen()
        self.assertTrue(IsValidPortNum(p1.contactURI.port))

    def test_aor_bindings(self):

        p1 = NoMediaSimpleCallsParty()
        p2 = NoMediaSimpleCallsParty()

        self.assertRaises(ValueError, p1.invite, p2)

        p1.listen()

        log.info('Incomplete raised, because we don\'t have an AOR yet.')

        self.assertRaises(Incomplete, p2.invite, p1)

        log.info('Set an AOR on p2')
        p2.aor = 'p2@test.com'
        self.assertRaises(Incomplete, p2.invite, p1)

        p1.aor = 'p1@test.com'
        inv1 = p2.invite(p1)
        inv2 = p2.invite(p1)

        del inv1
        del inv2


class TestPartyWeakReferences(SIPPartyTestCase):
    def test_weak_references(self):
        self.sub_test_weak_reference()

        tp = self.wtp()
        if tp:
            tp.close_all()

    def sub_test_weak_reference(self):
        owllog = logging.getLogger('OnlyWhenLocked')
        owllog.setLevel(logging.DEBUG)

        log.info('Check SIPTransport deletes cleanly')
        tp = SIPTransport()
        tp2 = SIPTransport('other_transport')
        self.assertIsNot(tp, tp2)
        w_tp2 = ref(tp2)
        w_tp = ref(tp)
        self.assertIs(w_tp(), tp)
        del tp
        gc.collect()
        self.assertIsNone(w_tp())
        del tp2
        gc.collect()
        self.assertIsNone(w_tp2())

        log.info('Check SIPTransport + Party delete cleanly')
        tp = SIPTransport()
        w_tp = ref(tp)
        self.assertIs(w_tp(), tp)
        p1 = NoMediaSimpleCallsParty()
        wp1 = ref(p1)
        self.assertIs(tp, p1.transport)
        del p1
        self.assertIsNone(wp1())
        del tp
        self.assertIsNone(w_tp())

        log.info('Check listening party deletes cleanly')
        p1 = NoMediaSimpleCallsParty()
        p1.listen()
        w_p1 = ref(p1)
        w_tp = ref(p1.transport)
        self.assertIs(w_p1(), p1)
        self.assertIs(w_tp(), p1.transport)
        del p1
        self.assertIsNone(w_p1())
        self.assertIsNone(w_tp())

        log.info('Check connected party deletes cleanly.')
        p1 = NoMediaSimpleCallsParty(aor=b'alice@atlanta.com')
        wp1 = ref(p1)
        p1.listen()
        self.wtp = ref(p1.transport)
        p2 = NoMediaSimpleCallsParty(aor=b'bob@biloxi.com')
        wtp2 = ref(p2.transport)
        self.assertIs(self.wtp(), wtp2())
        self.assertIsNotNone(self.wtp())

        invD = p2.invite(p1)
        w_inv = ref(invD)
        WaitFor(lambda: len(wp1().inCallDialogs) > 0)

        self.assertIsNotNone(w_inv())
        self.assertIs(w_inv(), invD)

        wp1 = ref(p1)
        wp2 = ref(p2)
        del p1
        del p2
        del invD
        gc.collect()
        self.assertIsNone(wp1())
        self.assertIsNone(wp2())
        WaitFor(lambda: w_inv() is None)
