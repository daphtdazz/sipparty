"""testprot.py

Unit tests for sip-party.

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
import os
import re
from six import (add_metaclass, binary_type as bytes, iteritems, PY2)
import sys
import unittest
from ..parse import ParseError
from ..sdp import sdpsyntax
from ..sip import (prot, components, Message, Header)
from ..sip.body import Body
from ..sip.components import URI
from ..sip.header import ContactHeader
from ..sip.prot import (Incomplete)
from ..sip.request import Request
from ..util import (Singleton, bglobals_g)
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestProtocol(SIPPartyTestCase):

    tag_pattern = b"tag=[\da-f]{8}"
    call_id_pattern = b"[\da-f]{6}-\d{14}"
    branch_pattern = b"branch=z9hG4bK[\da-f]{1,}"
    cseq_num_pattern = b"\d{1,10}"

    message_patterns = bglobals_g(locals())
    message_patterns.update(sdpsyntax.bdict)

    def assertEqualMessages(self, msga, msgb):
        stra = bytes(msga)
        strb = bytes(msgb)
        self.assertEqual(
            stra, strb, "\n{0!r}\nvs\n{1!r}\n---OR---\n{0}\nvs\n{1}"
            "".format(stra, strb))

    def testGeneral(self):
        aliceAOR = components.AOR(b"alice", b"atlanta.com")
        self.assertEqual(bytes(aliceAOR), b"alice@atlanta.com")
        bobAOR = components.AOR(b"bob", b"baltimore.com")

        self.assertRaises(AttributeError, lambda: Request.notareq)

        inviteRequest = Request.invite(uri__aor=bobAOR)
        self.assertEqual(
            bytes(inviteRequest), b"INVITE sip:bob@baltimore.com SIP/2.0")

        self.assertRaises(AttributeError, lambda: Message.notareg)

        invite = Message.invite()
        self.assertRaises(Incomplete, lambda: bytes(invite))
        old_branch = bytes(invite.viaheader.parameters.branch)
        invite.startline.uri = components.URI(aor=bobAOR)

        # Ideally just changing the URI should be enough to regenerate the
        # branch parameter, as it should be live.  However the branch
        # parameter will only notice if invite.startline changes, not if the
        # object at invite.startline changes, as it deliberately doesn't
        # recalculate its value automatically.
        sline = invite.startline
        invite.startline = None
        invite.startline = sline
        new_branch = bytes(invite.viaheader.parameters.branch)
        self.assertNotEqual(old_branch, new_branch)
        invite.fromheader.field.value.uri.aor.username = b"alice"
        invite.fromheader.field.value.uri.aor.host = b"atlanta.com"
        invite.viaheader.field.host.address = b"127.0.0.1"
        inv_bytes = bytes(invite)
        self.assertTrue(re.match(
                b"INVITE sip:bob@baltimore.com SIP/2.0\r\n"
                b"From: <sip:alice@atlanta.com>;%(tag_pattern)s\r\n"
                b"To: <sip:bob@baltimore.com>\r\n"
                b"Via: SIP/2.0/UDP 127.0.0.1;%(branch_pattern)s\r\n"
                # 6 random hex digits followed by a date/timestamp
                b"Call-ID: %(call_id_pattern)s\r\n"
                b"CSeq: %(cseq_num_pattern)s INVITE\r\n"
                b"Max-Forwards: 70\r\n" % self.message_patterns, inv_bytes),
            inv_bytes)

        self.assertEqual(
            bytes(invite.toheader), b"To: <sip:bob@baltimore.com>")
        self.assertEqual(
            bytes(invite.call_idheader),
            bytes(getattr(invite, "Call_IdHeader")))
        self.assertRaises(AttributeError, lambda: invite.notaheader)
        return

    def testParse(self):

        # self.pushLogLevel("header", logging.DEBUG)
        # self.pushLogLevel("message", logging.DEBUG)
        # self.pushLogLevel("parse", logging.DETAIL)
        # self.pushLogLevel('param', logging.DETAIL)
        # self.pushLogLevel('util', logging.DETAIL)

        invite = Message.invite()

        self.assertRaises(Incomplete, lambda: bytes(invite))

        # Check the bindings were set up correctly: the Request URI should be
        # the same object as the To URI.
        self.assertIsNotNone(invite.startline.uri)
        self.assertTrue(invite.startline.uri is invite.toheader.uri)
        turi = invite.toheader.uri
        nuri = URI()
        log.info("Set startline URI to something new.")
        invite.startline.uri = nuri
        self.assertTrue(
            invite.startline.uri is invite.toheader.uri, (
                id(invite.startline.uri), id(invite.toheader.uri)))
        # In python3 you can't use strings for these.
        if not PY2:
            self.assertRaises(
                ValueError,
                lambda: setattr(invite.startline, 'username', 'bob'))
        invite.startline.username = b"bob"
        self.assertEqual(invite.startline.username, invite.toheader.username)
        invite.startline.uri.aor.host = b"biloxi.com"
        invite.fromheader.field.value.uri.aor.username = b"alice"
        invite.fromheader.field.value.uri.aor.host = b"atlanta.com"
        invite.contactheader.uri = b"sip:localuser@127.0.0.1:5061"
        invite.max_forwardsheader.number = 55
        self.assertEqual(invite.contactheader.port, 5061)
        log.info("Set via header host.")
        self.assertEqual(invite.viaheader.port, 5061)

        invite_str = bytes(invite)
        log.info("Invite to stringify and parse: %r", invite_str)

        new_inv = Message.Parse(invite_str)
        self.assertEqualMessages(invite, new_inv)

        log.info("Establish bindings")
        new_inv.enableBindings()
        log.info("Add new VIA header")
        new_inv.addHeader(Header.via())
        self.assertEqual(new_inv.contactheader.port, 5061)
        self.assertEqual(new_inv.viaheader.port, 5061)
        self.assertEqual(
            bytes(new_inv.viaheader.field.host), b"127.0.0.1:5061")
        self.assertEqual(
            bytes(new_inv.viaheader.host.address), b"127.0.0.1")

        new_inv.viaheader.host = b"arkansas.com"
        new_inv.startline.uri.aor.username = b"bill"

        new_inv.addBody(
            Body(type=sdpsyntax.SIPBodyType, content=b"This is a message"))

        new_inv_bytes = bytes(new_inv)
        self.assertTrue(re.match(
            b"INVITE sip:bill@biloxi.com SIP/2.0\r\n"
            b"From: <sip:alice@atlanta.com>;%(tag_pattern)s\r\n"
            # Note that the To: URI hasn't changed because when the parse
            # happens a new uri gets created for each, and there's no link
            # between them.
            b"To: <sip:bill@biloxi.com>\r\n"
            b"Via: SIP/2.0/UDP arkansas.com\r\n"
            b"Via: SIP/2.0/UDP 127.0.0.1:5061;%(branch_pattern)s\r\n"
            # 6 random hex digits followed by a date/timestamp
            b"Call-ID: %(call_id_pattern)s\r\n"
            b"CSeq: %(cseq_num_pattern)s INVITE\r\n"
            b"Max-Forwards: 55\r\n"
            b"Content-Length: 17\r\n"
            b"Contact: <sip:alice@127.0.0.1:5061>\r\n"
            b"Content-Type: %(SIPBodyType)s\r\n"
            b"\r\n"
            b"This is a message$"
            b"" % self.message_patterns,
            new_inv_bytes), repr(new_inv_bytes))

    def testProt(self):
        for name, obj in iteritems(prot.__dict__):
            if name.endswith("range") or name in (b'STAR',):
                continue
            if isinstance(obj, bytes):
                try:
                    re.compile(obj)
                except re.error as exc:
                    self.fail("Failed to compile %r: %s: %r" % (
                        name, exc, obj))

        for ptrn, examples in (
                (prot.userinfo, (b'bob@',)),
                (prot.hostname, (b'biloxihostname.com',)),
                (prot.host, (b'biloxihost.com',)),
                (prot.hostport, (b'biloxible.com',)),
                (prot.addr_spec, (b'sip:bob@biloxi.com',)),
                (prot.SIP_URI, (b'sip:bob@biloxi.com',)),):
            cre = re.compile(ptrn)
            for example in examples:
                mo = cre.match(example)
                self.assertIsNotNone(
                    mo, "regex %r did not match %r" % (ptrn, example))
                self.assertEqual(len(mo.group(0)), len(example), (
                    "%d != %d: regex %r does not fully match %r." % (
                        (len(mo.group(0)), len(example), ptrn, example))))

    def testComponents(self):
        for cpnt, examples in (
                (components.DNameURI, (
                    (b"<sip:bob@biloxi.com>",),)),
                (Request, ((b'INVITE sip:bob@biloxi.com SIP/2.0',),)),
                (ContactHeader, (
                    (b'<sip:[::1]:5060;transport=UDP>',
                     b'Contact: <sip:[::1]:5060;transport=UDP>'),))):
            for example in examples:
                log.info("Test example %r", example)
                try:
                    cp = cpnt.Parse(example[0])
                except ParseError:
                    self.fail("%r failed to parse %r." % (
                        cpnt.__name__, example[0]))

                exp = example[1] if len(example) > 1 else example[0]
                self.assertEqual(exp, bytes(cp))

    def testMessageProperties(self):
        # self.pushLogLevel("vb", logging.DETAIL)
        # self.pushLogLevel("message", logging.DETAIL)
        inv = Message.invite()
        inv.bodies = [Body()]
        self.assertTrue(hasattr(inv, "Content_TypeHeader"))
        inv.unbindAll()
        self.assertEqual(len(inv._vb_forwardbindings), 0)
        self.assertEqual(len(inv._vb_backwardbindings), 0)
