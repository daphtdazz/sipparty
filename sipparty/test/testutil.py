"""tutil.py

Unit tests for sipparty utilities.

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
from six import PY2
import unittest
from .. import util
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestUtil(SIPPartyTestCase):

    def testEnum(self):
        en = util.Enum(("cat", "dog", "aardvark", "mouse"))

        aniter = en.__iter__()
        next = aniter.next if PY2 else aniter.__next__
        self.assertEqual(next(), "cat")
        self.assertEqual(next(), "dog")
        self.assertEqual(next(), "aardvark")
        self.assertEqual(next(), "mouse")
        self.assertRaises(StopIteration, lambda: next())

        self.assertEqual(en[0], "cat")
        self.assertEqual(en[1], "dog")
        self.assertEqual(en[2], "aardvark")
        self.assertEqual(en[3], "mouse")

        self.assertEqual(en.index("cat"), 0)
        self.assertEqual(en.index("dog"), 1)
        self.assertEqual(en.index("aardvark"), 2)
        self.assertEqual(en.index("mouse"), 3)

        self.assertEqual(en[1:3], ["dog", "aardvark"])

    def testBytesEnum(self):

        if not PY2:
            self.assertRaises(TypeError, lambda: util.AsciiBytesEnum(('cat',)))
            self.assertRaises(
                TypeError, lambda: util.AsciiBytesEnum(
                    (b'cat',), aliases={'cat': b'cat'}))
        be = util.AsciiBytesEnum(
            (b'cat', b'dog'), aliases={b'CAT': b'cat'})
        self.assertTrue(b'cat' in be)
        self.assertEqual(b'cat', be.cat)
        self.assertTrue(hasattr(be, 'cat'))
        self.assertTrue(hasattr(be, 'CAT'))

    def testb_globals(self):

        a_ascii_enum = util.AsciiBytesEnum((b'a', b'c'))
        a_normal_enum = util.Enum(('a', 'b'))
        a_normal_bytes_var = b'bytes'
        a_normal_string_var = 'string'

        gdict = util.bglobals_g(locals())
        self.assertTrue(b'a_ascii_enum.a' in gdict, gdict)
        self.assertTrue(b'a_ascii_enum.c' in gdict, gdict)
        self.assertTrue('a_normal_enum.a' in gdict, gdict)
        self.assertTrue('a_normal_enum.b' in gdict, gdict)
        # Bytes values have their keys converted to bytes also.
        self.assertTrue(b'a_normal_bytes_var' in gdict, gdict)
        self.assertTrue('a_normal_string_var' in gdict, gdict)

