"""testdialog.py

Unit tests for a SIP party.

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
import timeit
import time
import logging
import weakref
import unittest
import socket
from .. import (fsm, sip, util)
from ..sip import Dialog
from ..sip.dialogs import SimpleCall

log = logging.getLogger(__name__)


class TestDialog(unittest.TestCase):

    def testStandardDialog(self):
        dl = SimpleCall()
        self.assertRaises(AttributeError, lambda: dl.asdf)
        self.assertRaises(ValueError, dl.hit, 'initiate')
        self.assertEqual(dl.state, dl.States.Initial)
        iv = dl.sendRequestInvite
