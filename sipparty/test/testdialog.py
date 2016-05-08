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
import logging
from weakref import ref
from .setup import SIPPartyTestCase
from ..sip.components import (AOR, Host, URI)
from ..sip.dialogs import SimpleCall
from ..sip.siptransaction import TransactionManager
from ..sip.siptransport import SIPTransport

log = logging.getLogger(__name__)


class TestDialog(SIPPartyTestCase):

    def testStandardDialog(self):
        tp = SIPTransport()
        tm = TransactionManager()
        dl = SimpleCall(tp, tm)
        self.assertRaises(AttributeError, lambda: dl.asdf)
        self.assertRaises(ValueError, dl.hit, 'initiate')
        self.assertEqual(dl.state, dl.States.Initial)

        dl.from_uri = 'sip:user1@host'
        self.assertRaises(ValueError, dl.hit, 'initiate')
        log.info('%r', dl.from_uri)
        self.assertEqual(
            dl.from_uri,
            URI(absoluteURIPart=None, headers=b'', aor=AOR(
                username=b'user1', host=Host(address=b'host', port=None)),
                parameters=b'', scheme=b'sip'),
            dl.from_uri.aor)

    def sub_test_transaction_creation(self, depth):
        tp = SIPTransport()
        tm = TransactionManager()
        dl = SimpleCall(tp, tm)
        dl.from_uri = 'sip:user1@host'
        dl.to_uri = 'sip:user2@nowhere'
        dl.contact_uri = 'sip:user1'
        wrfs = ref(tp), ref(tm), ref(dl)

        if depth > 0:
            tp.listen_for_me()

            if depth > 1:
                dl.initiate(
                    remote_name='127.0.0.1', remote_port=9999)

        del tp
        del tm
        del dl
        for wrf in wrfs:
            self.assertIsNone(wrf())

    def create_sub_test(func, static_args):
        def dummy(self, *args):
            return func(self, *(static_args + args))
        return dummy

    for _ii in range(3):
        locals()['test_transaction_creation_depth_%d' % _ii] = create_sub_test(
            sub_test_transaction_creation, (_ii,))
