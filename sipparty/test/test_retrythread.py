"""tfsm.py

Unit tests for the SIP FSM.

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
import os
import sys
from weakref import ref

from six import PY2

from ..fsm.retrythread import RetryThread
from ..util import (WaitFor,)
from .base import (SIPPartyTestCase,)

log = logging.getLogger(__name__)


class TestRetryThread(SIPPartyTestCase):

    def setUp(self):
        super(TestRetryThread, self).setUp()
        self.retry = 0
        self.cleanup = 0
        self.done = False

        self.patch_clock()
        self.data_read = None

    def read_data(self, fd):
        self.data_read = os.read(fd, 4096)

    def test_retry_thread_fd(self):
        rt = RetryThread()
        rr, ww = os.pipe()

        rt.addInputFD(rr, self.read_data)
        os.write(ww, b'hello')
        WaitFor(lambda: self.data_read is not None)
        self.assertEqual(self.data_read, b'hello')

        rt.rmInputFD(rr)
        WaitFor(lambda: rt._rthr_thread is None)
        log.info('Test done')

    def test_retry_thread_tidy_up(self):

        rthr = RetryThread()
        self.assertIsNone(rthr._rthr_thread)
        rthr.addRetryTime(20)
        self.assertIsNotNone(rthr._rthr_thread)
        thr = rthr._rthr_thread
        wr = ref(rthr)
        del rthr
        WaitFor(lambda: wr() is None, action_each_cycle=gc.collect)
        WaitFor(lambda: not thr.is_alive())

    def test_exception_holding_retry_thread(self):

        def get_rthr_and_raise():
            rthr = RetryThread()
            self.wrthr = ref(rthr)
            rthr.addRetryTime(20)
            raise Exception('exception')

        try:
            get_rthr_and_raise()
        except Exception:
            rthr = self.wrthr()
            self.assertIsNotNone(rthr)
            self.wthr = rthr._rthr_thread
            self.assertIsNotNone(self.wthr)
            self.assertTrue(self.wthr.is_alive())
            del rthr
        else:
            self.assertFalse(True, 'expected an exception')

        if PY2:
            sys.exc_clear()
        # After dropping out of the except, the rthr should be tidied
        WaitFor(lambda: self.wrthr() is None)
        WaitFor(lambda: not self.wthr.is_alive())
