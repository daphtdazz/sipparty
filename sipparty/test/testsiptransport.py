"""tsiptransport.py

Unit tests for the SIP transport.

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
import time
import timeit
import logging
import unittest
import six

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)

import sipparty
from sipparty.sip import siptransport
SIPTransport = siptransport.SIPTransport


class TestSIPTransport(unittest.TestCase):

    def testSIPTransport(self):

        global rcvd_message
        rcvd_message = None
        def handler(message):
            global rcvd_message
            rcvd_message = message

        tp = SIPTransport()
        tp.addToHandler(uri, handler)
        laddr = tp.listen()

        tp.send("hello world", "127.0.0.1")
        tp.sendMessage(message, address)

if __name__ == "__main__":
    unittest.main()
