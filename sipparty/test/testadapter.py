"""testadapter.py

Test the adapter module.

Copyright 2016 David Park

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
from ..adapter import (
    AdaptToClass, AdapterOptionKeyConversion, AdapterProperty, ListConverter,
    NoSuchAdapterError, ProxyAdapter)
from .._adapter import (_AdapterManager)
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestAdapter(SIPPartyTestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_adapter_manager(self):
        m1 = _AdapterManager()
        m2 = _AdapterManager()
        self.assertIs(m1, m2)

    def test_adapter_property(self):

        self.assertRaises(TypeError, AdapterProperty, 'not-a-type')

        class Class2(object):
            def class2_method(self, alist):
                alist.append(1)

        class Class1(object):

            class2_version = AdapterProperty(Class2)

            def __init__(self):
                self.class1_attr1 = 1
                self.class1_attr2 = 2
                self.class1_children = []

        log.info('Register the adapters (just by creating the class).')
        class Class1ToClass2Adapter(ProxyAdapter):
            from_class = Class1
            to_class = Class2
            adaptations = (
                ('class2_attr1', 'class1_attr1', {
                    AdapterOptionKeyConversion: lambda x: x * 5
                }),
                ('class2_attr2', 'class1_attr2'),
                ('class2_children', 'class1_children', {
                    AdapterOptionKeyConversion: ListConverter(Class2)})
            )

        c1 = Class1()
        self.assertEqual(c1.class2_version.class2_attr1, 5)
        self.assertEqual(c1.class2_version.class2_attr2, 2)

        log.info('Demonstrate that the Class2 proxy can do Class2 things.')
        alist = []
        c1.class2_version.class2_method(alist)
        self.assertEqual(alist, [1])

        log.info('Show that a adapting a list was easy.')
        c1_1 = Class1()
        c1.class1_children = [Class1() for _ in range(3)]
        c1.class1_children[1].class1_attr1 = 2
        c1.class1_children[2].class1_attr1 = 3
        self.assertEqual(
            [child.class2_attr1
             for child in c1.class2_version.class2_children],
            [5, 10, 15])
