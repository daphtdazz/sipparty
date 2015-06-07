"""tmediasession.py

Test the media session.

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.      .
See the License for the specific language governing permissions and
limitations under the License.
"""
import logging
import six
import unittest
import vb
import sip
from sip import Session
from sip import mediasession

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)

bytes = six.binary_type


class TestSession(sip._util.TestCaseREMixin, unittest.TestCase):

    def setUp(self):
        self._ms_level = sip.mediasession.log.level
        sip.mediasession.log.setLevel(logging.DEBUG)

    def tearDown(self):
        sip.mediasession.log.setLevel(self._ms_level)

    def testBasicSession(self):
        return
        ms = Session("alice")
        ms.addSession()


if __name__ == "__main__":
    unittest.main()
