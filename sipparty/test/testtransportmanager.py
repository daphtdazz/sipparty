"""testtransportmanager.py

Unit tests for the transport manager code.

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
import socket
import timeit
import time
import logging
import unittest

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)

from sipparty import (util, fsm)
from sipparty.sip import transportmanager


class TestTM(unittest.TestCase, object):

    def setUp(self):
        util.log.setLevel(logging.DEBUG)

    def testSingleton(self):

        log.info("START TEST")
        s1 = util.Singleton()
        s2 = util.Singleton()
        self.assertTrue(s1 is s2)

        s3 = util.Singleton(name="name3")
        self.assertFalse(s1 is s3)
        s4 = util.Singleton(name="name3")
        self.assertTrue(s3 is s4)

        tm1 = transportmanager.ActiveTransportManager(name="atm1")
        self.assertTrue(tm1 is not None)
        tm2 = transportmanager.ActiveTransportManager(name="atm1")
        self.assertTrue(tm1 is tm2)

    def testBasicTM(self):

        pass
