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
import six
import logging
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
import unittest
import header
import components

log = logging.getLogger()


class TestHeaders(unittest.TestCase):

    def testContactHeaders(self):

        ch = header.Header.contact()

        for nonbool in (1, 2, "string", 0):
            self.assertRaises(ValueError,
                              lambda: setattr(ch, "isStar", nonbool))

        ch.isStar = True

        self.assertEqual(
            six.binary_type(ch),
            b"Contact: *")

        ch.isStar = False
        self.assertEqual(
            six.binary_type(ch),
            b"Contact: sip:")
        ch.field.value.uri.aor.username = b"bill"
        ch.field.value.uri.aor.host = b"billland.com"

        self.assertEqual(
            six.binary_type(ch),
            b"Contact: sip:bill@billland.com")


if __name__ == "__main__":
    unittest.main()
