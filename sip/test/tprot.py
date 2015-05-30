"""tprot.py

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
import six
import sys
import os
import re
import logging
import unittest
import pdb

# Get the root logger.
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger()

# Hack so we can always import the code we're testing.
sys.path.append(os.path.join(os.pardir, os.pardir))

import sip


class TestProtocol(unittest.TestCase):

    tag_pattern = "tag=[\da-f]{8}"
    call_id_pattern = "[\da-f]{6}-\d{14}"
    branch_pattern = "branch=z9hG4bK[\da-f]{1,}"
    cseq_num_pattern = "\d{1,10}"

    def assertEqualMessages(self, msga, msgb):
        stra = str(msga)
        strb = str(msgb)
        self.assertEqual(
            stra, strb, "\n{0!r}\nvs\n{1!r}\n---OR---\n{0}\nvs\n{1}"
            "".format(stra, strb))

    def testGeneral(self):

        aliceAOR = sip.components.AOR("alice", "atlanta.com")
        self.assertEqual(str(aliceAOR), "alice@atlanta.com")
        bobAOR = sip.components.AOR("bob", "baltimore.com")

        self.assertRaises(AttributeError, lambda: sip.Request.notareq)

        inviteRequest = sip.Request.invite(bobAOR)
        self.assertEqual(
            str(inviteRequest), "INVITE bob@baltimore.com SIP/2.0")

        self.assertRaises(AttributeError, lambda: sip.Message.notareg)

        invite = sip.Message.invite()
        self.assertTrue(re.match(
            "INVITE sip: SIP/2.0\r\n"
            "From: sip:;{3}\r\n"
            "To: sip:\r\n"
            "Via: SIP/2.0/UDP;{1}\r\n"
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: 70\r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern, TestProtocol.tag_pattern),
            str(invite)), "%r\n--OR--\n%s" % (str(invite), invite))
        old_branch = str(invite.viaheader.parameters.branch)
        invite.startline.uri = sip.components.URI(aor=bobAOR)

        # Ideally just changing the URI should be enough to regenerate the
        # branch parameter, as it should be live.  However the branch
        # parameter will only notice if invite.startline changes, not if the
        # object at invite.startline changes, as it deliberately doesn't
        # recalculate its value automatically.
        sline = invite.startline
        invite.startline = None
        invite.startline = sline
        new_branch = str(invite.viaheader.parameters.branch)
        self.assertNotEqual(old_branch, new_branch)
        invite.fromheader.field.value.uri.aor.username = "alice"
        invite.fromheader.field.value.uri.aor.host = "atlanta.com"
        invite.viaheader.field.host.host = "127.0.0.1"
        self.assertTrue(re.match(
            "INVITE sip:bob@baltimore.com SIP/2.0\r\n"
            "From: sip:alice@atlanta.com;{3}\r\n"
            "To: sip:bob@baltimore.com\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1;{1}\r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: 70\r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern, TestProtocol.tag_pattern),
            str(invite)), repr(str(invite)))

        self.assertEqual(str(invite.toheader), "To: sip:bob@baltimore.com")
        self.assertEqual(
            str(invite.call_idheader), str(getattr(invite, "Call_IdHeader")))
        self.assertRaises(AttributeError, lambda: invite.notaheader)

        resp = sip.message.Response(200)
        invite.applyTransform(resp, sip.transform.default[invite.type][200])

        self.assertTrue(re.match(
            "SIP/2.0 200 OK\r\n"
            "From: sip:alice@atlanta.com;{3}\r\n"
            "To: sip:bob@baltimore.com;{3}\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1;{1}\r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern, TestProtocol.tag_pattern),
            str(resp)), str(resp))

        sdp = sip.sdp

        return

    def testParse(self):

        invite = sip.Message.invite()
        invite.startline.uri.aor.username = "bob"
        invite.startline.uri.aor.host = "biloxi.com"
        invite.fromheader.field.value.uri.aor.username = "alice"
        invite.fromheader.field.value.uri.aor.host = "atlanta.com"
        log.debug("Set via header host.")
        invite.viaheader.field.host.host = "127.0.0.1"
        invite.viaheader.field.host.port = "5060"
        invite_str = str(invite)
        log.debug("Invite to stringify and parse: %r", invite_str)

        new_inv = sip.message.Message.Parse(invite_str)
        self.assertEqualMessages(invite, new_inv)

        new_inv.addHeader(sip.Header.via())
        new_inv.viaheader.host.host = "arkansas.com"

        new_inv.startline.uri.aor.username = "bill"

        self.assertTrue(re.match(
            "INVITE sip:bill@biloxi.com SIP/2.0\r\n"
            "From: sip:alice@atlanta.com;{3}\r\n"
            # Note that the To: URI hasn't changed because when the parse
            # happens a new uri gets created for each, and there's no link
            # between them.
            "To: sip:bob@biloxi.com\r\n"
            "Via: SIP/2.0/UDP arkansas.com\r\n"
            "Via: SIP/2.0/UDP 127.0.0.1:5060;{1}\r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: 70\r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern, TestProtocol.tag_pattern),
            str(new_inv)), repr(str(new_inv)))

    def testCall(self):

        caller = sip.Party()
        callee = sip.Party()

        return
        caller._sendinvite(callee)
        callee._respond(200)
        return

        caller.bye(callee)
        callee.respond(200)

        return

    def testSDP(self):

        # Minimal and currently ungodly SDP.
        sdpdata = (
            "v=0\r\n"
            "o=asdf\r\n"
            "s=fadsf\r\n"
            "t=asdf\r\n"
            "a=attr1\r\n"
            "a=attr2\r\n"
        )

        sdp = sip.sdp.Body.Parse(sdpdata)
        self.assertEqual(str(sdp), sdpdata)
        # !!! self.assertEqual(sdp.version, 0)

    def testEnum(self):
        en = sip._util.Enum(("cat", "dog", "aardvark", "mouse"))

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

        @six.add_metaclass(sip._util.CCPropsFor(("CPs", "CPList")))
        class CCPTestA(object):
            CPs = sip._util.Enum((1, 2))
            CPList = [1, 2]

        class CCPTestB(CCPTestA):
            CPs = sip._util.Enum((4, 5))
            CPList = [4, 5]

        class CCPTest1(CCPTestB):
            CPs = sip._util.Enum((3, 2))
            CPList = [3, 2]

        self.assertEqual(CCPTest1.CPs, sip._util.Enum((1, 2, 3, 4, 5)))

        # Expect the order of the update to start with the most nested, then
        # gradually get higher and higher.
        self.assertEqual(CCPTest1.CPList, [1, 2, 4, 5, 3])

    def testClassOrInstance(self):

        class MyClass(object):

            @sip._util.class_or_instance_method
            def AddProperty(cls_or_self, prop, val):
                setattr(cls_or_self, prop, val)

        inst = MyClass()
        MyClass.AddProperty("a", 1)
        inst.AddProperty("b", 2)
        MyClass.a == 1
        self.assertRaises(AttributeError, lambda: MyClass.b)
        self.assertEqual(inst.a, 1)
        self.assertEqual(inst.b, 2)


if __name__ == "__main__":
    sys.exit(unittest.main())
