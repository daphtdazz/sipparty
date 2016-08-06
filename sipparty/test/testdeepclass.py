"""Unit tests for the deep class.

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
from numbers import Integral
from ..deepclass import (DeepClass, dck)
from ..vb import ValueBinder
from .setup import SIPPartyTestCase

log = logging.getLogger(__name__)


class TestDeepClass(SIPPartyTestCase):

    def testVBInteraction(self):

        class TDObj(object):
            pass

        class TD(object):

            def __init__(self, name):
                super(TD, self).__init__()
                self._td_attr = name

            def __get__(self, obj, cls):
                assert obj is not None
                return getattr(obj, self._td_attr)

            def __set__(self, obj, val):
                assert obj is not None
                return setattr(obj, self._td_attr, val)

        class TVBDC(
                DeepClass("_tvbdc_", {
                    "attrA": {
                        dck.descriptor: TD,
                        dck.gen: TDObj
                    },
                    "attrB": {
                        dck.descriptor: TD,
                        dck.gen: TDObj
                    },
                }),
                ValueBinder):
            vb_bindings = (
                ("attrA", "attrB"),)

        log.info('Make a TVDBC')
        testVbdc = TVBDC()
        log.info('Delete the TVDBC')
        del testVbdc

        log.info('Make a TVDBC again')
        testVbdc = TVBDC()
        self.assertIsNotNone(testVbdc.attrA)
        self.assertTrue(testVbdc.attrA is testVbdc.attrB)

    def test_empty_prop(self):

        log.info(
            'Test a deepclass subclass has correct initial values for empty '
            'attributes, and attribute \'name\' which originally was broken')

        class TestDeepClass(DeepClass('_tdc_', {
                'attr1': {},
                'integral_attr': {
                    dck.check: lambda x: isinstance(x, Integral)},
                'name': {}
        })):
            pass

        tdc = TestDeepClass()
        for attr in ('attr1', 'integral_attr', 'name'):
            self.assertTrue(hasattr(tdc, attr), attr)
            self.assertIs(getattr(tdc, attr), None, attr)

    def test_repr_recursion(self):

        class TestDeepClass(DeepClass('_tdc_', {
            'attr1': {},
        })):
            pass

        dc1 = TestDeepClass()
        dc2 = TestDeepClass()
        dc1.attr1 = dc2
        dc2.attr1 = dc1
        dc1_repr = repr(dc1)
        self.assertRegexpMatches(
            dc1_repr,
            'TestDeepClass\(attr1=TestDeepClass\(attr1=<DC [0-9a-f]+>\)\)')

    def test_checked_descriptors(self):

        class TestDescriptor(object):

            def __init__(self, name):
                self.int_name = name

            def __get__(self, obj, cls):
                return getattr(obj, self.int_name)

            def __set__(self, obj, val):
                setattr(obj, self.int_name, val / 2)

        class TestDeepClass2(DeepClass('_tdc2_', {
                'attr1': {
                    dck.check: lambda x: x % 2 == 0,
                    dck.descriptor: TestDescriptor}
        })):
            pass

        tdc2 = TestDeepClass2()
        self.assertRaises(ValueError, setattr, tdc2, 'attr1', 1)
        tdc2.attr1 = 2
        self.assertEqual(tdc2.attr1, 1)
