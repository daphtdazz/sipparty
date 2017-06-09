"""testdialog.py

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
from __future__ import absolute_import

import logging
from six import next
from weakref import ref
from .base import SIPPartyTestCase
from ..fsm import UnexpectedInput
from ..sip.components import (AOR, Host, URI)
from ..sip.dialogs import SimpleClientDialog, SimpleServerDialog
from ..sip.siptransport import AORHandler, SIPTransport
from ..sip.standardtimers import StandardTimers
from ..util import WaitFor

log = logging.getLogger(__name__)


class TestDialog(AORHandler, SIPPartyTestCase):

    def setUp(self):
        super(TestDialog, self).setUp()
        self.rcode = None

    def fsm_dele_handle_invite(self, fsm, *args, **kwargs):
        if self.rcode is not None:
            log.info('Delegate is rejecting')
            return fsm.hit('reject', self.rcode, *args, **kwargs)

        log.info('Call default delegate implementation')
        return fsm.fsm_dele_handle_invite(*args, **kwargs)

    def new_dialog_from_request(self, req):
        log.info('Create new dialog for %s request', req.type)
        return SimpleServerDialog(
            from_uri=req.ToHeader.uri, to_uri=req.FromHeader.uri,
            transport=self.wtp(),
            delegate=self)

    #
    # =================== TESTS ===============================================
    #
    def testStandardDialog(self):
        tp = SIPTransport()
        dl = SimpleServerDialog(tp)
        self.assertRaises(AttributeError, lambda: dl.asdf)

        self.expect_log('ValueError exception')
        self.assertRaises(UnexpectedInput, dl.hit, 'initiate')
        self.assertEqual(dl.state, dl.States.Initial)

        dl.from_uri = 'sip:user1@host'
        self.expect_log('ValueError exception')
        self.assertRaises(UnexpectedInput, dl.hit, 'initiate')
        log.info('%r', dl.from_uri)
        self.assertEqual(
            dl.from_uri,
            URI(absoluteURIPart=None, headers=b'', aor=AOR(
                username=b'user1', host=Host(address=b'host', port=None)),
                parameters=b'', scheme=b'sip'),
            dl.from_uri.aor)

    def sub_test_transaction_creation(self, depth):
        log.info('sub_test_transaction_creation %d' % depth)
        tp = SIPTransport()
        self.wtp = ref(tp)
        dl = SimpleClientDialog(tp)
        dl.from_uri = 'sip:user1@host'
        dl.to_uri = 'sip:user2@host'
        tp.addDialogHandlerForAOR(dl.to_uri.aor, self)

        wrfs = self.wtp, ref(dl)

        def inner(tp, dl):
            ld = tp.listen_for_me(port=0)
            if depth == 0:
                return

            dl.initiate(remote_name=ld.name, remote_port=ld.port)
            dl.waitForStateCondition(
                lambda st: st == dl.States.InDialog)
            WaitFor(lambda: len(tp.establishedDialogs) == 2)

            log.info('wait for in dialog')
            for _dl in tp.establishedDialogs.values():
                _dl.waitForStateCondition(
                    lambda st: st == _dl.States.InDialog)

            if depth == 1:
                return

        inner(tp, dl)

        del tp
        del dl
        WaitFor(lambda: all(wrf() is None for wrf in wrfs))

    def create_sub_test(func, static_args):  # noqa
        def dummy(self, *args):
            return func(self, *(static_args + args))
        return dummy

    for _ii in range(3):
        locals()['test_transaction_creation_depth_%d' % _ii] = create_sub_test(
            sub_test_transaction_creation, (_ii,))


class TestDialogMockedSockets(SIPPartyTestCase):

    def setUp(self):
        super(TestDialogMockedSockets, self).setUp()
        self.patch_retrythread_select()
        self.patch_socket()
        self.patch_clock()

    def test_no_remote_party(self):
        """Test attempting to contact an uncontactable remote party."""
        tp = SIPTransport()
        dl = SimpleClientDialog(tp)
        dl.from_uri = 'sip:me@local'
        dl.to_uri = 'sip:then@uncontactable-host'

        log.info('Send first INVITE')
        dl.initiate(remote_name='127.0.0.1', remote_port=12345)
        self.assertEqual(tp.messages_sent, 1)

        log.info('Increment time and see us timeout')
        sts = StandardTimers()
        giveup_time, = tuple(sts.standard_timer_giveup_gen())
        assert self.clock_time == 0
        self.clock_time = giveup_time

        dl.waitForStateCondition(lambda st: st == dl.States.Terminated)
        # We only resend once because we coalesce resends.
        self.assertEqual(tp.messages_sent, 2)
        self.assertIsNone(dl.response)

    def test_no_remote_party_user_cancels(self):
        """Attempt to contact an uncontactable remote party but give up."""
        tp = SIPTransport()
        dl = SimpleClientDialog(tp)
        dl.from_uri = 'sip:me@local'
        dl.to_uri = 'sip:then@uncontactable-host'

        log.info('Send first INVITE')
        dl.initiate(remote_name='127.0.0.1', remote_port=12345)
        self.assertEqual(tp.messages_sent, 1)

        log.info('Increment time and see us retry')
        sts = StandardTimers()
        retry_time = next(sts.standard_timer_retransmit_gen())
        self.clock_time = retry_time
        self.wait_for(lambda: tp.messages_sent == 2)

        dl.terminate('User cancelled')
        self.assertEqual(dl.state, dl.States.Terminated)

        self.assertEqual(dl.termination_reason, 'User cancelled')
