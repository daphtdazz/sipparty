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
import sys
import os
import re
import logging
import unittest
import setup
from setup import SIPPartyTestCase
from six import binary_type as bytes, iteritems, add_metaclass
from sipparty import (util, sip, vb, ParseError, Request)
from sipparty.sip import (prot, components)
from sipparty.sip.components import URI
from sipparty.sip.prot import (Incomplete)

log = logging.getLogger(__name__)
log.setLevel(logging.DETAIL)


class TestProtocol(SIPPartyTestCase):

    tag_pattern = "tag=[\da-f]{8}"
    call_id_pattern = "[\da-f]{6}-\d{14}"
    branch_pattern = "branch=z9hG4bK[\da-f]{1,}"
    cseq_num_pattern = "\d{1,10}"

    def assertEqualMessages(self, msga, msgb):
        stra = bytes(msga)
        strb = bytes(msgb)
        self.assertEqual(
            stra, strb, "\n{0!r}\nvs\n{1!r}\n---OR---\n{0}\nvs\n{1}"
            "".format(stra, strb))

    def testGeneral(self):
        aliceAOR = sip.components.AOR("alice", "atlanta.com")
        self.assertEqual(bytes(aliceAOR), "alice@atlanta.com")
        bobAOR = sip.components.AOR("bob", "baltimore.com")

        self.assertRaises(AttributeError, lambda: sip.Request.notareq)

        inviteRequest = sip.Request.invite(bobAOR)
        self.assertEqual(
            bytes(inviteRequest), "INVITE bob@baltimore.com SIP/2.0")

        self.assertRaises(AttributeError, lambda: sip.Message.notareg)

        invite = sip.Message.invite()
        self.assertRaises(Incomplete, lambda: bytes(invite))
        old_branch = bytes(invite.viaheader.parameters.branch)
        invite.startline.uri = sip.components.URI(aor=bobAOR)

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
        invite.fromheader.field.value.uri.aor.username = "alice"
        invite.fromheader.field.value.uri.aor.host = "atlanta.com"
        invite.viaheader.field.host.address = "127.0.0.1"
        self.assertTrue(re.match(
            "INVITE sip:bob@baltimore.com SIP/2.0\r\n"
            "From: <sip:alice@atlanta.com>;{3}\r\n"
            "To: <sip:bob@baltimore.com>\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1;{1}\r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: 70\r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern, TestProtocol.tag_pattern),
            bytes(invite)), repr(bytes(invite)))

        self.assertEqual(bytes(invite.toheader), "To: <sip:bob@baltimore.com>")
        self.assertEqual(
            bytes(invite.call_idheader),
            bytes(getattr(invite, "Call_IdHeader")))
        self.assertRaises(AttributeError, lambda: invite.notaheader)
        return

    def testParse(self):

        self.pushLogLevel("header", logging.DEBUG)
        #self.pushLogLevel("vb", logging.DEBUG)
        self.pushLogLevel("message", logging.DETAIL)
        #self.pushLogLevel("field", logging.INFO)
        self.pushLogLevel("parse", logging.DEBUG)
        #self.pushLogLevel("deepclass", logging.DEBUG)
        #self.pushLogLevel("util", logging.DEBUG)

        invite = sip.Message.invite()

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
        invite.startline.username = "bob"
        self.assertEqual(invite.startline.username, invite.toheader.username)
        invite.startline.uri.aor.host = "biloxi.com"
        invite.fromheader.field.value.uri.aor.username = "alice"
        invite.fromheader.field.value.uri.aor.host = "atlanta.com"
        invite.contactheader.uri = "sip:localuser@127.0.0.1:5061"
        invite.max_forwardsheader.number = 55
        self.assertEqual(invite.contactheader.port, 5061)
        log.debug("Set via header host.")
        self.assertEqual(invite.viaheader.port, 5061)

        invite_str = bytes(invite)
        log.debug("Invite to stringify and parse: %r", invite_str)

        new_inv = sip.message.Message.Parse(invite_str)
        self.assertEqualMessages(invite, new_inv)

        new_inv.addHeader(sip.Header.via())
        self.assertEqual(new_inv.contactheader.port, 5061)
        self.assertEqual(new_inv.viaheader.port, 5061)
        self.assertEqual(
            bytes(new_inv.viaheader.field.host), b"127.0.0.1:5061")
        self.assertEqual(
            bytes(new_inv.viaheader.host.address), b"127.0.0.1")

        new_inv.viaheader.host = "arkansas.com"
        new_inv.startline.uri.aor.username = "bill"

        self.assertTrue(re.match(
            "INVITE sip:bill@biloxi.com SIP/2.0\r\n"
            "From: <sip:alice@atlanta.com>;{3}\r\n"
            # Note that the To: URI hasn't changed because when the parse
            # happens a new uri gets created for each, and there's no link
            # between them.
            "To: <sip:bill@biloxi.com>\r\n"
            "Via: SIP/2.0/UDP arkansas.com\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5061;{1}\r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: 55\r\n"
            "Contact: <sip:alice@127.0.0.1:5061>\r\n"
            "\r\n$".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern, TestProtocol.tag_pattern),
            bytes(new_inv)), repr(bytes(new_inv)))

    def testEnum(self):
        en = util.Enum(("cat", "dog", "aardvark", "mouse"))

        aniter = en.__iter__()
        self.assertEqual(aniter.next(), "cat")
        self.assertEqual(aniter.next(), "dog")
        self.assertEqual(aniter.next(), "aardvark")
        self.assertEqual(aniter.next(), "mouse")
        self.assertRaises(StopIteration, lambda: aniter.next())

        self.assertEqual(en[0], "cat")
        self.assertEqual(en[1], "dog")
        self.assertEqual(en[2], "aardvark")
        self.assertEqual(en[3], "mouse")

        self.assertEqual(en.index("cat"), 0)
        self.assertEqual(en.index("dog"), 1)
        self.assertEqual(en.index("aardvark"), 2)
        self.assertEqual(en.index("mouse"), 3)

        self.assertEqual(en[1:3], ["dog", "aardvark"])

    def testCumulativeProperties(self):

        @add_metaclass(util.CCPropsFor(("CPs", "CPList", "CPDict")))
        class CCPTestA(object):
            CPs = util.Enum((1, 2))
            CPList = [1, 2]
            CPDict = {1: 1, 2: 2}

        class CCPTestB(CCPTestA):
            CPs = util.Enum((4, 5))
            CPList = [4, 5]
            CPDict = {4: 4, 3: 3}

        class CCPTest1(CCPTestB):
            CPs = util.Enum((3, 2))
            CPList = [3, 2]
            CPDict = {2: 2, 3: 5}

        self.assertEqual(CCPTestA.CPs, util.Enum((1, 2)))
        self.assertEqual(CCPTestB.CPs, util.Enum((1, 2, 4, 5)))
        self.assertEqual(CCPTest1.CPs, util.Enum((1, 2, 3, 4, 5)))

        self.assertEqual(CCPTestA.CPDict, {1: 1, 2: 2})
        self.assertEqual(CCPTestB.CPDict, {1: 1, 2: 2, 3: 3, 4: 4})
        self.assertEqual(CCPTest1.CPDict, {1: 1, 2: 2, 3: 5, 4: 4})

        # Expect the order of the update to start with the most nested, then
        # gradually get higher and higher.
        self.assertEqual(CCPTest1.CPList, [1, 2, 4, 5, 3])

    def testClassOrInstance(self):

        class MyClass(object):

            @util.class_or_instance_method
            def AddProperty(cls_or_self, prop, val):
                setattr(cls_or_self, prop, val)

        inst = MyClass()
        MyClass.AddProperty("a", 1)
        inst.AddProperty("b", 2)
        MyClass.a == 1
        self.assertRaises(AttributeError, lambda: MyClass.b)
        self.assertEqual(inst.a, 1)
        self.assertEqual(inst.b, 2)

    def testProt(self):
        for name, obj in iteritems(prot.__dict__):
            if name.endswith("range") or name in ('STAR',):
                continue
            if isinstance(obj, bytes):
                try:
                    re.compile(obj)
                except re.error as exc:
                    self.fail("Failed to compile %r: %s: %r" % (
                        name, exc, obj))

        for ptrn, examples in (
                (prot.userinfo, ('bob@',)),
                (prot.hostname, ('biloxihostname.com',)),
                (prot.host, ('biloxihost.com',)),
                (prot.hostport, ('biloxible.com',)),
                (prot.addr_spec, ('sip:bob@biloxi.com',)),
                (prot.SIP_URI, ('sip:bob@biloxi.com',)),):
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
                    "<sip:bob@biloxi.com>",)),
                (Request, ('INVITE sip:bob@biloxi.com SIP/2.0',)),
                (sip.header.Header, (
                    'Contact: <sip:[::1]:5060;transport=UDP>',))):
            for example in examples:
                try:
                    cp = cpnt.Parse(example)
                except ParseError:
                    self.fail("%r failed to parse %r." % (
                        cpnt.__name__, example))

                self.assertEqual(example, bytes(cp))

if __name__ == "__main__":
    sys.exit(unittest.main())
