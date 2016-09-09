"""base.py

unittest customizations for the sipparty test cases.

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

import gc
import logging
import re
from six import (iteritems, PY2)
import sys
import unittest
from ..fsm.retrythread import RetryThread
from ..sip.siptransport import SIPTransport
if PY2:
    from mock import (MagicMock, patch)  # noqa
else:
    from unittest.mock import (MagicMock, patch)  # noqa

log = logging.getLogger(__name__)
sipparty = sys.modules['sipparty']


class TestCaseREMixin(object):

    def assertMatchesPattern(self, value, pattern):
        cre = re.compile(pattern)
        mo = cre.match(value)
        if mo is None:
            pvalue = self._tcrem_prettyFormat(value)
            ppatt = self._tcrem_prettyFormat(pattern)
            self.assertIsNotNone(
                mo, "%s \nDoes not match\n%s" % (pvalue, ppatt))

    def _tcrem_prettyFormat(self, string):
        return repr(string).replace("\\n", "\\n'\n'")


class SIPPartyTestCase(TestCaseREMixin, unittest.TestCase):

    Clock = MagicMock()

    def __init__(self, *args, **kwargs):
        super(SIPPartyTestCase, self).__init__(*args, **kwargs)
        self._sptc_logLevels = {}
        self._sptc_searchedModules = None

    def assertIsNotNone(self, exp, *args, **kwargs):
        if hasattr(super(SIPPartyTestCase, self), 'assertIsNotNone'):
            return super(SIPPartyTestCase, self).assertIsNotNone(
                exp, *args, **kwargs)

        return self.assertTrue(exp is not None)

    def expect_log(self, log_info):
        log.warning('EXPECT LOG %s', log_info)

    def setUp(self):
        super(SIPPartyTestCase, self).setUp()
        self.Clock.return_value = 0

    def tearDown(self):
        self.popAllLogLevels()

        if hasattr(super(SIPPartyTestCase, self), "tearDown"):
            super(SIPPartyTestCase, self).tearDown()

        RetryThread().cancel()

        # Speed things up a bit by doing a gc collect.
        gc.collect()
        SIPTransport.wait_for_no_instances(timeout_s=2)
        RetryThread.wait_for_no_instances(timeout_s=2)

    def pushLogLevelToSubMod(self, module, sub_module_name, level):

        firstModule, _, submodules = sub_module_name.partition(".")
        mdr = dir(module)
        if firstModule in mdr:
            sm = getattr(module, firstModule)
            if len(submodules) > 0:
                return self.pushLogLevelToSubMod(sm, submodules, level)
            lg = getattr(sm, "log")
            currLevel = lg.level
            lg.setLevel(level)
            return currLevel

        # Need to search for the submodule in all modules.
        for attr in mdr:
            if attr in self._sptc_searchedModules:
                continue
            self._sptc_searchedModules.add(attr)
            attr = getattr(module, attr)
            if type(attr) != type(sipparty):
                continue

            log.detail("Look at module %r", attr)
            res = self.pushLogLevelToSubMod(attr, sub_module_name, level)
            if res is not None:
                return res

    def setLogLevel(self, module_name, level):
        self._sptc_searchedModules = set()
        lastLevel = self.pushLogLevelToSubMod(sipparty, module_name, level)
        self._sptc_searchedModules = None
        if lastLevel is None:
            raise AttributeError("No logger found for module %r" % module_name)
        return lastLevel

    def pushLogLevel(self, module_name, level):
        log.debug("Push log level %r to %r", level, module_name)
        lastLevel = self.setLogLevel(module_name, level)
        if module_name not in self._sptc_logLevels:
            self._sptc_logLevels[module_name] = []

        self._sptc_logLevels[module_name].append(lastLevel)
        log.debug("Current level for %r %r", module_name, lastLevel)

    def popAllLogLevels(self):
        for mod, levels in iteritems(self._sptc_logLevels):
            log.debug("Reset %r log level to %r", mod, levels[0])
            self.setLogLevel(mod, levels[0])
            del levels[:]
