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
from ..fsm import fsmtimer, retrythread
from ..fsm.retrythread import RetryThread
from ..sip.siptransport import SIPTransport
from ..transport import base as transport_base
from ..transport.mocksock import SocketMock
from ..util import Timeout, WaitFor
if PY2:
    from mock import (MagicMock, Mock, patch)  # noqa
else:
    from unittest.mock import (MagicMock, Mock, patch)  # noqa

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

    # Faster than a mock
    def Clock(self):
        return self.clock_time

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

    def patch_clock(self):
        pp = patch.object(fsmtimer, 'Clock', new=self.Clock)
        pp.start()
        self.addCleanup(pp.stop)
        pp = patch.object(retrythread, 'Clock', new=self.Clock)
        pp.start()
        self.addCleanup(pp.stop)
        self.clock_time = 0
        self.addCleanup(setattr, self, 'clock_time', 0)

    def patch_socket(self):
        SocketMock.test_case = self
        self.addCleanup(setattr, SocketMock, 'test_case', None)
        socket_patch = patch.object(
            transport_base, 'socket_class', spec=type, new=SocketMock)
        socket_patch.start()
        self.addCleanup(socket_patch.stop)

    def tearDown(self):
        self.popAllLogLevels()

        getattr(super(SIPPartyTestCase, self), "tearDown", lambda: None)()

        RetryThread().cancel()

        exc = None
        for ii in range(4):
            log.debug('Doing GC collect')
            gc.collect()
            log.debug('Done GC collect')
            try:
                SIPTransport.wait_for_no_instances(timeout_s=0.1)
                RetryThread.wait_for_no_instances(timeout_s=0.1)
            except Timeout as ex:
                exc = ex
                continue
            else:
                break
        else:
            raise exc

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

    def wait_for(self, condition, **kwargs):

        try:
            WaitFor(condition, **kwargs)
        except Timeout:
            self.assertTrue(condition(), "Condition did not become true.")
