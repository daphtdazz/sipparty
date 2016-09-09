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
from __future__ import absolute_import

import logging
from ..vb import (BindingAlreadyExists, NoSuchBinding, ValueBinder)
from .base import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestVB(SIPPartyTestCase):

    def testBindings(self):
        VB = ValueBinder

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
        self.assertRaises(NoSuchBinding, lambda: a.unbind("b", "b.x"))
        self.assertRaises(BindingAlreadyExists,
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

        a.bind("x", "y")
        a.x = 2
        self.assertEqual(a.y, 2)
        a.bind("x", "yy")
        self.assertEqual(a.yy, 2)
        a.unbindAll()
        self.assertEqual(len(a._vb_forwardbindings), 0)
        self.assertEqual(len(a._vb_backwardbindings), 0)

    def testDependentBindings(self):

        class A(ValueBinder):
            vb_dependencies = [
                ("b", ["c"])
            ]

            def __setattr__(self, attr, val):
                if attr == 'c':
                    return setattr(self.b, attr, val)
                return super(A, self).__setattr__(attr, val)

        a = A()
        b = ValueBinder()
        a.b = b
        b.c = 2
        self.assertEqual(a.c, 2)
        self.assertEqual(a.b.c, 2)
        a.bind("c", "d")
        self.assertEqual(a.d, 2)

        # But now we change b, and d should be changed.
        bb = ValueBinder()
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

        # Test that we can delete delegated attributes.
        self.assertTrue(hasattr(a, "c"))
        self.assertTrue(hasattr(b, "c"))
        self.assertTrue(hasattr(a, "d"))
        del a.c
        self.assertFalse(hasattr(a, "c"))
        self.assertFalse(hasattr(b, "c"))
        self.assertIsNone(a.d)

        a.unbind("c", "d")
        a.e = 10
        self.assertEqual(a.c, 10)
        self.assertEqual(b.c, 10)

        a.unbind("e", "c")
        for ivb in (a, b, bb):
            self.assertEqual(len(ivb._vb_backwardbindings), 0)
            self.assertEqual(len(ivb._vb_forwardbindings), 0)

        a = A()
        a.b = ValueBinder()
        a.bind("d", "c")
        a.d = 1
        self.assertEqual(a.b.c, 1)
        a.unbindAll()
        a.bind("d", "c")
        a.d = None
        self.assertEqual(a.c, None)
        a.unbindAll()
        a.bind("d", "c")
        del a.d
        self.assertEqual(a.c, None)
        a.unbindAll()
        a.bind("d", "c")
        del a.b
        a.unbindAll()

    def testOrphans(self):
        """Test that when a parent is deleted, the children can be rebound.
        """
        a, b, c = [ValueBinder() for ii in range(3)]

        a.bind("b.val", "val")
        c.bind("b.val", "val")
        a.b = b
        b.val = 2
        self.assertEqual(a.val, 2)

        log.info("Orphan 'b' by deleting parent.")
        del a

        log.info("Check b has been unbound and can be rebound.")
        self.assertTrue(b.vb_parent is None)
        c.b = b
        self.assertFalse(b.vb_parent is None)
        self.assertEqual(c.val, 2)
        c.unbindAll()
        self.assertTrue(b.vb_parent is None)

    def testMultipleBindings(self):
        """Test that we can bind something to more than one thing."""
        a = ValueBinder()

        a.bind("val", "val1")
        a.bind("val", "val2")

        a.val = 5
        self.assertEqual(a.val1, 5)
        self.assertEqual(a.val2, 5)

    def testRefreshBindings(self):

        a, ab = [ValueBinder() for _ in range(2)]
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
        self.assertEqual(a.c, 4)
        self.assertEqual(a.a, 2)
        self.assertEqual(a.d, 5)

    def testBoundThroughBindings(self):
        a, aa, ab, aaa, aba = [ValueBinder() for _ in range(5)]

        a.bind("a.a.a", "c")
        a.a = aa
        a.a.a = aaa
        a.a.a.a = 4
        self.assertEqual(a.c, 4)

        # Now if we switch in ab for a.a then what happens to a.c?
        ab.a = aba
        ab.a.a = 5
        a.a = ab
        self.assertEqual(a.c, 5)

    def testValuesWithDifferentParentsAreNotUnlinked(self):

        a, aa, ab, aaa, aba = [ValueBinder() for _ in range(5)]

        a.bind("a", "b.a")
        a.a = aa
        a.b = ab
        self.assertTrue(a.b.a is aa)
        a.bind("a.d", "d")
        self.assertTrue(aa.vb_parent is a)
        self.assertEqual(len(aa._vb_forwardbindings), 1)
        a.b.a = 6
        self.assertTrue(aa.vb_parent is a)
        self.assertEqual(len(aa._vb_forwardbindings), 1)

    def testExceptionsInBindings(self):
        a, aa, ab, aaa, aba = [ValueBinder() for _ in range(5)]

        a.bind(
            "b", "c", transformer=lambda x: int(x),
            ignore_exceptions=(ValueError,))
        a.b = 2
        self.assertEqual(a.c, 2)
        a.b = "not"
        self.assertEqual(a.b, "not")
        self.assertEqual(a.c, 2)

    def test_binding_to_non_vb(self):
        NonVBType = type('NonVB', (), {})

        a = ValueBinder()
        b = ValueBinder()
        a.b = b
        log.info(
            'Check binding through a non-VB type raises and doesn\'t update '
            'bindings.')
        a.b.c = NonVBType()
        self.assertRaises(TypeError, a.bind, 'b.c.d', 'b1')
        self.assertIsNone(a.b.vb_parent)

        log.info('Check we can bind to it after removing the offending entry.')
        a.b.c = None
        a.bind('b.c.d', 'b1')

    def test_inserting_non_vb(self):
        self.skipTest(
            'Raising TypeError on setting bad type instance in the binding '
            'path not yet supported.')
        NonVBType = type('NonVB', (), {})

        a = ValueBinder()
        b = ValueBinder()
        a.b = b
        log.info('Check inserting a non-VB object raises.')
        a.bind('b.c.d', 'b1')
        self.assertRaises(TypeError, setattr, a, 'b', NonVBType())
