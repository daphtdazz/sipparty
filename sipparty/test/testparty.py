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
from ..sip.dialogs import SimpleClientDialog, SimpleServerDialog
from ..sip.prot import Incomplete
from ..sip.siptransport import SIPTransport
from ..transport import (IsValidPortNum, NameLoopbackAddress)
from ..util import (abytes, WaitFor)
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestParty(SIPPartyTestCase):

    def assertIsNone(self, exp, *args, **kwargs):
        if hasattr(super(TestParty, self), 'assertIsNone'):
            return super(TestParty, self).assertIsNone(exp, *args, **kwargs)

        return self.assertTrue(exp is None)

    def testBasicPartyTCP(self):
        self.skipTest('TCP not yet implemented')
        self.subTestBasicParty(SOCK_STREAM, )

    def test_basic_party_udpipv4(self):
        self.subTestBasicParty(SOCK_DGRAM, '127.0.0.1')

    def testBasicPartyUDPIPv6(self):
        self.subTestBasicParty(SOCK_DGRAM, '::1')

    def test_basic_party_udpipv4_stop_after_creation(self):
        self.subTestBasicParty(
            SOCK_DGRAM, '127.0.0.1', stop_point='after creation')

    def test_basic_party_udpipv4_stop_after_invite(self):
        self.subTestBasicParty(
            SOCK_DGRAM, '127.0.0.1', stop_point='after first invite')

    def test_basic_party_udpipv4_stop_after_listen(self):
        self.subTestBasicParty(
            SOCK_DGRAM, '127.0.0.1', stop_point='after first listen')

    def test_basic_party_udpipv4_stop_after_call(self):
        self.subTestBasicParty(
            SOCK_DGRAM, '127.0.0.1', stop_point='after first call')

    def subTestBasicParty(self, sock_type, contact_name, stop_point=None):

        assert sock_type == SOCK_DGRAM
        log.info('Listen with type %r', sock_type)

        BasicParty = type(
            'BasicParty', (Party,), {
                'ClientDialog': SimpleClientDialog,
                'ServerDialog': SimpleServerDialog,
                'MediaSession': type(
                    'LoopbackSingleRTPSession', (SingleRTPSession,), {
                        'DefaultName': NameLoopbackAddress
                    }
                )
            }
        )

        log.info('Start p1')
        p1 = BasicParty(aor=b'alice@atlanta.com')
        wtp = ref(p1.transport)
        wp1 = ref(p1)
        log.info('..and p2')
        p2 = BasicParty(aor=b'bob@biloxi.com')
        wp2 = ref(p2)

        self.assertIs(p1.transport, p2.transport)

        if stop_point == 'after creation':
            del p1, p2
            for wrf in (wp1, wp2, wtp):
                self.assertIsNone(wrf())
            return

        log.info('p1 listens')
        p1.listen(name=contact_name, sock_type=sock_type, port=0)
        log.info('p2 invites p1')

        if stop_point == 'after first listen':
            del p1, p2
            for wrf in (wp1, wp2, wtp):
                self.assertIsNone(wrf())
            return

        invD = p2.invite(p1)
        winvD = ref(invD)
        WaitFor(lambda: winvD().state == winvD().States.InDialog, 1)
        WaitFor(lambda: len(wp1().inCallDialogs) > 0)
        WaitFor(
            lambda:
            wp1().inCallDialogs[0].state ==
            wp1().inCallDialogs[0].States.InDialog)

        if stop_point == 'after first invite':
            del p1, p2, invD
            for wrf in (wp1, wp2, winvD, wtp):
                log.info('check wrf %s is free', wrf)
                WaitFor(lambda: wrf() is None)
                self.assertIsNone(wrf())
            return

        WaitFor(lambda: len(wp1().inCallDialogs) == 1)
        self.assertEqual(len(p2.inCallDialogs), 1)

        log.info('p1 terminates')
        invD.terminate()
        WaitFor(lambda: winvD().state == winvD().States.Terminated, 1)

        if stop_point == 'after first call':
            del p1, p2, invD
            for wrf in (wp1, wp2, winvD, wtp):
                log.info('check wrf %s is free', wrf)
                WaitFor(lambda: wrf() is None)
                self.assertIsNone(wrf())
            return

        # Try another call.
        p3 = BasicParty(
            aor=b'charlie@charlesville.com',
            contact_uri__address=abytes(contact_name))
        p3.listen(sock_type=sock_type, name=contact_name, port=0)
        self.assertTrue(p3.transport is p1.transport)
        self.assertTrue(p3.transport is p2.transport)
        invD3to2 = p2.invite(p3)

        WaitFor(lambda: invD3to2.state == invD3to2.States.InDialog, 1)

        WaitFor(lambda: len(p3.inCallDialogs) == 1)
        self.assertEqual(len(p2.inCallDialogs), 1)
        self.assertEqual(len(p1.inCallDialogs), 0)

        log.info('Terminate invD3to2')
        invD3to2.terminate()
        WaitFor(lambda: invD3to2.state == invD3to2.States.Terminated, 1)

        self.assertEqual(len(p3.inCallDialogs), 0)
        self.assertEqual(len(p2.inCallDialogs), 0)
        self.assertEqual(len(p1.inCallDialogs), 0)

        return

    def test_double_listen(self):
        tp = SIPTransport()
        p1 = NoMediaSimpleCallsParty()
        self.assertRaises(Incomplete, p1.listen)

        log.info('test listening twice uses a single socket')
        p1.uri = 'sip:p1@test.com'
        p1.listen(port=0)
        port = p1.contact_uri.port

        p2 = NoMediaSimpleCallsParty()
        p2.uri = 'sip:p2@test.com'
        p2.listen(port=0)
        self.assertEqual(p2.contact_uri.port, port)
        self.assertEqual(tp.listen_socket_count, 1)

        log.info('Now unlisten from both')
        p2.unlisten()
        self.assertEqual(tp.listen_socket_count, 1)
        p1.unlisten()
        self.assertEqual(tp.listen_socket_count, 0)

    def test_no_media_party(self):

        log.info('Create two new no-media parties.')
        p1 = NoMediaSimpleCallsParty(uri='sip:p1@test.com')
        p1.listen(port=0)
        self.assertTrue(IsValidPortNum(p1.contact_uri.port))

    def test_aor_bindings(self):

        p1 = NoMediaSimpleCallsParty(uri='sip:p1@test.com')
        p2 = NoMediaSimpleCallsParty()
        p3 = NoMediaSimpleCallsParty('sip:p3@test.com')

        self.assertRaises(ValueError, p1.invite, p2)
        self.assertRaises(ValueError, p1.invite, p2)

        p1.listen(port=0)
        self.assertEqual(p2.transport.listen_socket_count, 1)
        self.assertEqual(p2.transport.connected_socket_count, 0)

        log.info('Incomplete raised, because we don\'t have an AOR yet.')

        self.assertRaises(Incomplete, p2.invite, p1)
        self.assertEqual(p2.transport.connected_socket_count, 0)

        log.info('Set an AOR on p2')
        p2.aor = 'p2@test.com'
        inv1 = p2.invite(p1)

        WaitFor(lambda: inv1.state == inv1.States.InDialog)
        self.assertEqual(p3.transport.connected_socket_count, 2)

        inv2 = p2.invite(p1)
        WaitFor(lambda: inv2.state == inv2.States.InDialog)
        self.assertEqual(p3.transport.connected_socket_count, 2)

        log.info(
            "Check that we get a good exception when attempting to invite "
            "someone who isn't listening")
        self.assertRaises(ValueError, p3.invite, p2)
        self.assertRaises(ValueError, p3.invite, p2)
        p2.listen(port=0)
        inv3 = p3.invite(p2)
        WaitFor(lambda: inv3.state == inv2.States.InDialog)

        log.info("Check we've actually only opened one listen socket")
        self.assertEqual(p3.transport.listen_socket_count, 1)

        log.info("And still only two connected sockets due to reuse.")
        self.assertEqual(p3.transport.connected_socket_count, 2)

    def test_server_terminates(self):

        class DialogDelegate:
            def fsm_dele_handle_invite(self, dialog, invite):
                self.dialog = dialog
                self.invite = invite

        server_dialog_delegate = DialogDelegate()

        party = NoMediaSimpleCallsParty(
            display_name_uri='sip:alice@atlanta.com',
            dialog_delegate=server_dialog_delegate)
        party.listen(port=0)

        party2 = NoMediaSimpleCallsParty('sip:bob@biloxi.com')

        party2.invite(party)
        WaitFor(lambda: hasattr(server_dialog_delegate, 'invite'))

        server_dialog_delegate.dialog.hit('accept')
        server_dialog_delegate.dialog.waitForStateCondition(
            lambda st: st == server_dialog_delegate.dialog.States.InDialog)
        server_dialog_delegate.dialog.terminate()
        server_dialog_delegate.dialog.waitForStateCondition(
            lambda st: st == server_dialog_delegate.dialog.States.Terminated)


class TestPartyWeakReferences(SIPPartyTestCase):
    def test_weak_references(self):
        self.sub_test_weak_reference()

        tp = self.wtp()
        if tp:
            tp.close_all()

    def sub_test_weak_reference(self):

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
        p1 = NoMediaSimpleCallsParty(aor='p1@test.com')
        p1.listen(port=0)
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
        p1.listen(port=0)
        self.wtp = ref(p1.transport)
        p2 = NoMediaSimpleCallsParty(aor=b'bob@biloxi.com')
        wtp2 = ref(p2.transport)
        self.assertIs(self.wtp(), wtp2())
        self.assertIsNotNone(self.wtp())

        p2.invite(p1)
        WaitFor(lambda: len(wp1().inCallDialogs) > 0)
