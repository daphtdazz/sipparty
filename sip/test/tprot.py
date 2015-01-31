import sys
import os
import re
import unittest
import pdb

# Hack so we can always import the code we're testing.
sys.path.append(os.path.join(os.pardir, os.pardir))

import sip


class TestProtocol(unittest.TestCase):

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
        invite.startline.uri = sip.prot.URI(aor=bobAOR)
        invite.fromheader.value.uri = sip.prot.URI(aor=aliceAOR)
        self.assertTrue(re.match(
            "INVITE sip:bob@baltimore.com SIP/2.0\r\n"
            "From: sip:alice@atlanta.com\r\n"
            "To: sip:bob@baltimore.com\r\n"
            "Via: \r\n"
            # 6 random hex digits followed by a date/timestamp
            "Call-ID: [\da-f]{6}-\d{14}\r\n"
            "CSeq: \r\n"
            "Max-Forwards: \r\n",
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
        VB = sip._util.ValueBinder

        a, b, c = [VB() for ii in range(3)]

        a.bind("x", "y", bothways=True)
        a.x = 1
        self.assertEqual(a.y, 1)
        a.y = 2
        self.assertEqual(a.x, 2)
        a.unbind("x")
        a.y = 3
        self.assertEqual(a.x, 2)

        a.bind("x", "b.y", bothways=True)
        a.b = b
        a.x = 5
        self.assertEqual(a.b.y, 5)
        a.b.y = 6
        self.assertEqual(a.x, 6)
        a.unbind("x")
        a.b.y = 7
        self.assertEqual(a.x, 6)
        self.assertEqual(a.b.y, 7)
        self.assertEqual(len(a._bindings), 0)
        self.assertEqual(len(a.b._bindings), 0)

        a.b.c = c
        a.bind("b.x", "b.c.x")
        b.x = 7
        self.assertEqual(a.b.x, 7)
        self.assertEqual(c.x, 7)
        self.assertRaises(sip._util.NoSuchBinding, lambda: a.unbind("b"))
        self.assertRaises(sip._util.BindingAlreadyExists,
                          lambda: a.bind("b.x", "b.c.d.x"))


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
