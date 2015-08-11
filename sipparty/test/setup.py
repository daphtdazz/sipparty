"""setup.py

Setup for the sip party logging code.

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
import unittest
from six import iteritems
import sipparty

log = logging.getLogger(__name__)


class SIPPartyTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super(SIPPartyTestCase, self).__init__(*args, **kwargs)
        self._sptc_logLevels = {}
        self._sptc_searchedModules = None

    def tearDown(self):
        self.popAllLogLevels()

        if hasattr(super(SIPPartyTestCase, self), "tearDown"):
            super(SIPPartyTestCase, self).tearDown()

    def pushLogLevelToSubMod(self, module, subModuleName, level):

        firstModule, _, submodules = subModuleName.partition(".")
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
                #log.detail("%r not a module, is %r", attr, attr.__class__)
                continue
            log.detail("Look at module %r", attr)
            res = self.pushLogLevelToSubMod(attr, subModuleName, level)
            if res is not None:
                return res

    def setLogLevel(self, moduleName, level):
        self._sptc_searchedModules = set()
        lastLevel = self.pushLogLevelToSubMod(sipparty, moduleName, level)
        self._sptc_searchedModules = None
        if lastLevel is None:
            raise AttributeError("No logger found for module %r" % moduleName)
        return lastLevel

    def pushLogLevel(self, moduleName, level):
        log.debug("Push log level %r to %r", level, moduleName)
        lastLevel = self.setLogLevel(moduleName, level)
        if moduleName not in self._sptc_logLevels:
            self._sptc_logLevels[moduleName] = []

        self._sptc_logLevels[moduleName].append(lastLevel)
        log.debug("Current level for %r %r", moduleName, lastLevel)

    def popAllLogLevels(self):
        for mod, levels in iteritems(self._sptc_logLevels):
            log.debug("Reset %r log level to %r", mod, levels[0])
            self.setLogLevel(mod, levels[0])
            del levels[:]
