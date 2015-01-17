import sys
import os
import re
import unittest

# Hack so we can always import the code we're testing.
sys.path.append(os.path.join(os.pardir, os.pardir))

import sip


class TestProtocol(unittest.TestCase):

    def testGeneral(self):

        aliceAOR = sip.prot.AOR("alice", "atlanta.com")
        self.assertEqual(str(aliceAOR), "alice@atlanta.com")
        bobAOR = sip.prot.AOR("bob", "baltimore.com")

        self.assertRaises(AttributeError, lambda: sip.prot.Request.notareq)

        inviteRequest = sip.prot.Request.invite(bobAOR)
        self.assertEqual(
            str(inviteRequest), "INVITE bob@baltimore.com SIP/2.0")

        import pdb
        #pdb.set_trace()
        self.assertRaises(AttributeError, lambda: sip.prot.Message.notareg)

        invite = sip.prot.Message.invite()
        invite.startline.aor = bobAOR
        self.assertTrue(re.match(
            "INVITE bob@baltimore.com SIP/2.0\r\n"
            "From: \r\n"
            "To: \r\n"
            "Via: \r\n"
            "Call-ID: [\da-f]{6}-\d{14}\r\n"
            "CSeq: \r\n"
            "Max-Forwards: \r\n",
            str(invite)), str(invite))
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

        #invite = sip.prot.Request(reqLine


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