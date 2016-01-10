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
    AdapterOptionKeyConversion, AdapterProperty, ProxyAdapter,
    NoSuchAdapterError)
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

        self.pushLogLevel('_adapter', logging.DETAIL)
        self.pushLogLevel('adapter', logging.DETAIL)
        self.pushLogLevel('util', logging.DEBUG)
        class Class2(object):
            pass

        class Class1(object):

            class2_version = AdapterProperty(Class2)

            def __init__(self):
                self.class1_attr1 = 1
                self.class1_attr2 = 2

        class Class1ToClass2Adapter(ProxyAdapter):
            from_class = Class1
            to_class = Class2
            adaptations = (
                ('class2_attr1', 'class1_attr1', {
                    AdapterOptionKeyConversion: lambda x: x * 5
                }),
                ('class2_attr2', 'class1_attr2')
            )
        c1toc2adapter = Class1ToClass2Adapter()
        c1 = Class1()
        self.assertEqual(c1.class2_version.class2_attr1, 5)
        self.assertEqual(c1.class2_version.class2_attr2, 2)
