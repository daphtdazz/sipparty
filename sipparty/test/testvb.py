"""tvb.py

Unit tests for variable bindings.

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
from setup import SIPPartyTestCase
from sipparty import vb

# If main get the root logger.
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)


class TestVB(SIPPartyTestCase):

    def setUp(self):
        super(TestVB, self).setUp()
        self.pushLogLevel("vb", logging.DEBUG)

    def testBindings(self):
        VB = vb.ValueBinder

        a, b, c, d, D = [VB() for ii in range(5)]

        a.bind("x", "y")
        a.x = 1
        self.assertEqual(a.y, 1)
        a.y = 2
        self.assertEqual(a.x, 1)
        a.bind("y", "x")
        self.assertEqual(a.x, 2)
        a.unbind("x", "y")
        a.x = 4
        self.assertEqual(a.y, 2)
        a.y = 3
        self.assertEqual(a.x, 3)
        a.unbind("y", "x")

        a.bind("x", "b.y")
        a.b = b
        a.x = 5
        self.assertEqual(a.b.y, 5)
        a.b.y = 6
        self.assertEqual(a.x, 5)
        a.unbind("x", "b.y")
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
        self.assertRaises(vb.NoSuchBinding, lambda: a.unbind("b", "b.x"))
        self.assertRaises(vb.BindingAlreadyExists,
                          lambda: a.bind("b.x", "b.c.x"))
        a.unbind("b.x", "b.c.x")

        del b.x
        a.b.c.x = 7
        a.bind("b.c.x", "d.x")
        a.d = d
        self.assertEqual(a.d.x, 7)
        # Bind the other way to check we don't do a silly loop.
        a.bind("d.x", "b.c.x")
        a.d = D
        self.assertEqual(a.d.x, 7)

        e = VB()
        e.bind("a", "ea")
        e.a = a
        self.assertEqual(e.ea, a)

    def testDependentBindings(self):

        class A(vb.ValueBinder):
            vb_dependencies = [
                ("b", ["c"])
            ]

            def __setattr__(self, attr, val):
                if attr == 'c':
                    return setattr(self.b, attr, val)
                return super(A, self).__setattr__(attr, val)

        a = A()
        b = vb.ValueBinder()
        a.b = b
        b.c = 2
        self.assertEqual(a.c, 2)
        a.bind("c", "d")
        self.assertEqual(a.d, 2)

        # But now we change b, and d should be changed.
        bb = vb.ValueBinder()
        bb.c = 5
        a.b = bb
        self.assertEqual(a.d, 5)
        self.assertEqual(len(b._vb_backwardbindings), 0)
        self.assertEqual(len(b._vb_forwardbindings), 0)

        # Test binding to delegate attributes the other way.
        a.bind("e", "c")
        a.e = 7
        self.assertEqual(a.d, 7)
        self.assertEqual(bb.c, 7)
        a.b = b
        self.assertEqual(b.c, 7)
        a.e = 9
        self.assertEqual(bb.c, 7)
        self.assertEqual(a.d, 9)
        self.assertEqual(b.c, 9)

        a.unbind("c", "d")
        a.e = 10
        self.assertEqual(a.c, 10)
        self.assertEqual(b.c, 10)
        self.assertEqual(a.d, 9)

        a.unbind("e", "c")
        for ivb in (a, b, bb):
            self.assertEqual(len(ivb._vb_backwardbindings), 0)
            self.assertEqual(len(ivb._vb_forwardbindings), 0)

    def testOrphans(self):
        """Test that when a parent is deleted, the children can be rebound.
        """
        a, b, c = [vb.ValueBinder() for ii in range(3)]

        a.bind("b.val", "val")
        c.bind("b.val", "val")
        a.b = b
        b.val = 2
        self.assertEqual(a.val, 2)

        # Orphan b by deleting a.
        del a

        # Now reassign b to c.
        c.b = b
        self.assertEqual(c.val, 2)

    def testMultipleBindings(self):
        """Test that we can bind something to more than one thing."""
        a = vb.ValueBinder()

        a.bind("val", "val1")
        a.bind("val", "val2")

        a.val = 5
        self.assertEqual(a.val1, 5)
        self.assertEqual(a.val2, 5)

    def testParentBindings(self):
        a, ab = [vb.ValueBinder() for _ in range(2)]

        ab.vb_parent = a

        ab.bind(".c", "c")
        a.c = 2
        self.assertEqual(ab.c, 2)
        self.assertTrue(ab.vb_parent is a)
        self.assertTrue(a.vb_parent is ab)
        ab.unbind(".c", "c")
        self.assertEqual(len(ab._vb_forwardbindings), 0)
        self.assertEqual(len(ab._vb_backwardbindings), 0)
        self.assertEqual(len(a._vb_forwardbindings), 0)
        self.assertEqual(len(a._vb_backwardbindings), 0)

    def testRefreshBindings(self):

        a, ab = [vb.ValueBinder() for _ in range(2)]
        a.bind("a", "c", lambda x: x * 2 if x is not None else None)
        a.bind("b.d", "d")
        a.b = ab
        a.a = 2
        a.b.d = 5
        self.assertEqual(a.d, 5)
        self.assertEqual(a.c, 4)
        a.c = 3
        self.assertEqual(a.c, 3)
        self.assertEqual(a.a, 2)
        a.d = 6
        self.assertEqual(a.b.d, 5)
        self.assertEqual(a.d, 6)
        a.refreshBindings()
        self.assertEqual(a.c, 2)
        self.assertEqual(a.a, 2)
        self.assertEqual(a.d, 5)

if __name__ == "__main__":
    sys.exit(unittest.main())
