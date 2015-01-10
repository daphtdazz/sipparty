import sys
import os
import unittest

# Hack so we can always import the code we're testing.
sys.path.append(os.path.join(os.pardir, os.pardir))

import sip


class TestProtocol(unittest.TestCase):

    def testGeneral(self):

        meURL = sip.prot.URL("dmp", "greenparksoftware.com")
        self.assertEqual(str(meURL), "dmp@greenparksoftware.com")

        self.assertRaises(sip.prot.ProtocolError,
                          lambda: sip.prot.requesttype.notareq)

        reqLine = sip.prot.RequestLine(
            sip.prot.requesttype.invite, meURL)
        self.assertEqual(
            str(reqLine), "INVITE dmp@greenparksoftware.com SIP/2.0\r\n")


if __name__ == "__main__":
    unittest.main()
