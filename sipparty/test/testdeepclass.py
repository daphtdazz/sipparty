"""testdeepclass.py

Unit tests for sip-party.

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
import sys
import os
import re
import logging
import unittest
import setup
from setup import SIPPartyTestCase
from six import binary_type as bytes, iteritems, add_metaclass
from sipparty import (util, sip, vb, ParseError, Request)
from sipparty.deepclass import (DeepClass, dck)
from sipparty.sip import (prot, components)
from sipparty.sip.components import URI

log = logging.getLogger(__name__)
# log.setLevel(logging.DETAIL)


class TestDeepClass(SIPPartyTestCase):

    def testVBInteraction(self):

        # self.pushLogLevel("vb", logging.DEBUG)
        # self.pushLogLevel("deepclass", logging.DEBUG)

        class TDObj(object):
            pass

        class TD(object):

            def __init__(self, attr):
                super(TD, self).__init__()
                self._td_attr = attr

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
                vb.ValueBinder):
            vb_bindings = (
                ("attrA", "attrB"),)

        testVbdc = TVBDC()
        self.assertIsNotNone(testVbdc.attrA)
        self.assertTrue(testVbdc.attrA is testVbdc.attrB)
