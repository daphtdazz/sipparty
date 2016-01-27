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
from six import (binary_type as bytes)
from ..sip import (prot, Header)
from ..sip.components import (Host)
from ..sip.header import ContactHeader
from ..vb import ValueBinder
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestHeaders(SIPPartyTestCase):

    def testContactHeaders(self):

        # self.pushLogLevel("header", logging.DEBUG)

        ch = Header.contact()

        for nonbool in (1, 2, "string", 0):
            self.assertRaises(ValueError,
                              lambda: setattr(ch, "isStar", nonbool))

        ch.isStar = True

        self.assertEqual(bytes(ch), b"Contact: *")

        ch.isStar = False
        self.assertRaises(prot.Incomplete, lambda: bytes(ch))
        ch.field.username = b"bill"
        ch.field.host = b"billland.com"

        self.assertEqual(
            bytes(ch),
            b"Contact: <sip:bill@billland.com>")

        nh = ContactHeader.Parse(bytes(ch))
        self.assertFalse(nh.isStar)
        self.assertEqual(
            bytes(ch),
            b"Contact: <sip:bill@billland.com>")
        self.assertEqual(
            ch.field.value.uri.aor.host, Host(address=b"billland.com"))

    def testBindingContactHeaders(self):

        pvb = ValueBinder()

        pvb.bind("hostaddr", "ch.address")
        pvb.bind("ch.address", "hostaddr2")

        pvb.ch = Header.contact()
        pvb.hostaddr = b'atlanta.com'
        self.assertEqual(pvb.ch.address, b'atlanta.com')
        self.assertEqual(pvb.ch.field.value.uri.aor.host.address,
                         b'atlanta.com')
        self.assertEqual(pvb.hostaddr2, b'atlanta.com')

    def testNumHeader(self):
        cont_len_hdr = Header.content_length()
        self.assertEqual(bytes(cont_len_hdr), b"Content-Length: 0")
