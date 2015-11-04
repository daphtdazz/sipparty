"""theader.py

Unit tests for SIP headers.

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
import six
import unittest
from setup import SIPPartyTestCase
from ..sip import (prot, Header)
from ..sip.components import (Host)
from ..vb import ValueBinder

log = logging.getLogger(__name__)


class TestHeaders(SIPPartyTestCase):

    def testContactHeaders(self):

        # self.pushLogLevel("header", logging.DEBUG)

        ch = Header.contact()

        for nonbool in (1, 2, "string", 0):
            self.assertRaises(ValueError,
                              lambda: setattr(ch, "isStar", nonbool))

        ch.isStar = True

        self.assertEqual(six.binary_type(ch), b"Contact: *")

        ch.isStar = False
        self.assertRaises(prot.Incomplete, lambda: six.binary_type(ch))
        ch.field.username = b"bill"
        ch.field.host = b"billland.com"

        self.assertEqual(
            six.binary_type(ch),
            b"Contact: <sip:bill@billland.com>")

        nh = Header.Parse(six.binary_type(ch))
        self.assertEqual(
            six.binary_type(ch),
            b"Contact: <sip:bill@billland.com>")
        self.assertEqual(
            ch.field.value.uri.aor.host, Host("billland.com"))

    def testBindingContactHeaders(self):

        pvb = ValueBinder()

        pvb.bind("hostaddr", "ch.address")
        pvb.bind("ch.address", "hostaddr2")

        pvb.ch = Header.contact()
        pvb.hostaddr = "atlanta.com"
        self.assertEqual(pvb.ch.address,
                         "atlanta.com")
        self.assertEqual(pvb.ch.field.value.uri.aor.host.address,
                         "atlanta.com")
        self.assertEqual(pvb.hostaddr2, "atlanta.com")

    def testNumHeader(self):
        cont_len_hdr = Header.content_length()
        self.assertEqual(bytes(cont_len_hdr), b"Content-Length: 0")

if __name__ == "__main__":
    unittest.main()
