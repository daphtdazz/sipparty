import sys
import os
import re
import unittest
import pdb

# Hack so we can always import the code we're testing.
sys.path.append(os.path.join(os.pardir, os.pardir))

import sip


class TestProtocol(unittest.TestCase):

    call_id_pattern = "[\da-f]{6}-\d{14}"
    branch_pattern = "branch=z9hG4bK[\da-f]{1,}"
    cseq_num_pattern = "\d{1,10}"

    def testGeneral(self):

        aliceAOR = sip.prot.AOR("alice", "atlanta.com")
        self.assertEqual(str(aliceAOR), "alice@atlanta.com")
        bobAOR = sip.prot.AOR("bob", "baltimore.com")

        self.assertRaises(AttributeError, lambda: sip.Request.notareq)

        inviteRequest = sip.Request.invite(bobAOR)
        self.assertEqual(
            str(inviteRequest), "INVITE bob@baltimore.com SIP/2.0")

        self.assertRaises(AttributeError, lambda: sip.Message.notareg)

        invite = sip.Message.invite()
        self.assertTrue(re.match(
            "INVITE None SIP/2.0\r\n"
            "From: sip:\r\n"
            "To: \r\n"
            "Via: SIP/2.0/UDP;{1}\r\n"
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: \r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern),
            str(invite)), str(invite))
        old_branch = str(invite.viaheader.parameters.branch)
        invite.startline.uri = sip.prot.URI(aor=bobAOR)
        new_branch = str(invite.viaheader.parameters.branch)
        self.assertNotEqual(old_branch, new_branch)
        invite.fromheader.uri.aor.username = "alice"
        invite.fromheader.uri.aor.host = "atlanta.com"
        self.assertTrue(re.match(
            "INVITE sip:bob@baltimore.com SIP/2.0\r\n"
            "From: sip:alice@atlanta.com\r\n"
            "To: sip:bob@baltimore.com\r\n"
            "Via: SIP/2.0/UDP atlanta.com;{1}\r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: {0}\r\n"
            "CSeq: {2} INVITE\r\n"
            "Max-Forwards: \r\n".format(
                TestProtocol.call_id_pattern, TestProtocol.branch_pattern,
                TestProtocol.cseq_num_pattern),
            str(invite)), str(invite))

        self.assertEqual(str(invite.toheader), "To: sip:bob@baltimore.com")
        self.assertEqual(
            str(invite.call_idheader), str(getattr(invite, "Call-IDHeader")))
        self.assertRaises(AttributeError, lambda: invite.notaheader)

        return

        caller = sip.Party()
        callee = sip.Party()

        invite = caller.build(sip.prot.requesttype.invite)

        self.assertEqual(invite, "")
        return

        tohdr = sip.prot.HeaderForName("To", reqLine)
        return
        self.assertTrue(isinstance(tohdr, sip.prot.ToHeader))
        self.assertEqual(str(tohdr), "To: dmp@greenparksoftware.com")

        # invite = sip.prot.Request(reqLine

    def testBindings(self):
        VB = sip.vb.ValueBinder

        a, b, c, d, D = [VB() for ii in range(5)]

        a.bind("x", "y")
        a.x = 1
        self.assertEqual(a.y, 1)
        a.y = 2
        self.assertEqual(a.x, 1)
        a.bind("y", "x")
        self.assertEqual(a.x, 2)
        a.unbind("x")
        a.x = 4
        self.assertEqual(a.y, 2)
        a.y = 3
        self.assertEqual(a.x, 3)
        a.unbind("y")

        a.bind("x", "b.y")
        a.b = b
        a.x = 5
        self.assertEqual(a.b.y, 5)
        a.b.y = 6
        self.assertEqual(a.x, 5)
        a.unbind("x")
        a.x = 7
        self.assertEqual(a.x, 7)
        self.assertEqual(a.b.y, 6)

        # Do some naughty internal checks.
        self.assertEqual(len(a._vb_forwardbindings), 0)
        self.assertEqual(len(a._vb_backwardbindings), 0)
        self.assertEqual(len(a.b._vb_forwardbindings), 0)
        self.assertEqual(len(a.b._vb_backwardbindings), 0)

        a.b.c = c
        a.bind("b.x", "b.c.x")
        b.x = 7
        self.assertEqual(a.b.x, 7)
        self.assertEqual(c.x, 7)
        self.assertRaises(sip.vb.NoSuchBinding, lambda: a.unbind("b"))
        self.assertRaises(sip.vb.BindingAlreadyExists,
                          lambda: a.bind("b.x", "b.c.d.x"))
        a.unbind("b.x")

        del b.x
        a.b.c.x = 7
        a.bind("b.c.x", "d.x")
        a.d = d
        self.assertEqual(a.d.x, 7)
        # Bind the other way to check we don't do a silly loop.
        a.bind("d.x", "b.c.x")
        a.d = D
        self.assertEqual(a.d.x, 7)

    def del_testAttrDict(self):

        ad = sip._util.AttributeDict()
        ad.anattr = 2
        self.assertEqual(ad.anattr, 2)
        self.assertEqual(ad["anattr"], 2)

        ada = sip._util.AttributeDict()
        adb = sip._util.AttributeDict()

        ad.a = ada
        ad.b = adb
        ad.bind("a.x", "b.y")
        pdb.set_trace()
        ad.a.x = 2
        self.assertEqual(ad.b.y, 2)
        adb = sip._util.AttributeDict()
        self.assertRaises(AttributeError, lambda: adb.y)
        ad.b = adb
        self.assertEqual(ad.b.y, 2)
        self.assertEqual(adb.y, 2)
        ad.unbind("a.x")

if __name__ == "__main__":
    sys.exit(unittest.main())


caller = sipparty.SipParty()
callee = sipparty.SipParty()

callee.listen()

caller.register()

callee.receiveRegister()
callee.respond(200)

caller.receiveResponse(200)

caller.invite()
callee.respond(100)
callee.respond(180)
caller.receiveResponse(100)
caller.receiveResponse(180)

callee.bye()
caller.respond(200)
