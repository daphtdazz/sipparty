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
import threading
import time
from weakref import ref

from six import PY2

from ..fsm import retrythread
from ..fsm.retrythread import RetryThread
from ..util import (Timeout, WaitFor,)
from .base import (ANY, MagicMock, patch, SIPPartyTestCase,)

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
        try:
            WaitFor(lambda: not thr.is_alive())
        finally:
            log.info('mark points: %s', getattr(thr, 'rthr_mark_points', None))
            log.info('Extra diags: %s', getattr(thr, 'extra_diags', None))

    def test_exception_holding_retry_thread(self):

        class TException(Exception):
            pass

        def get_rthr_and_raise():
            rthr = RetryThread(name='bert', no_reuse=True)
            self.wrthr = ref(rthr)
            rthr.addRetryTime(20)

            raise TException('exception')

        try:
            get_rthr_and_raise()
        except TException:
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

        try:
            WaitFor(lambda: not self.wthr.is_alive())
        except Timeout:
            raise
        finally:
            log.info(
                'mark points: %s',
                getattr(self.wthr, 'rthr_mark_points', None))
            log.info(
                'Extra diags: %s', getattr(self.wthr, 'extra_diags', None))

    def test_max_select_wait(self):

        self.assertLess(RetryThread.max_select_wait, 20)

        cvar = threading.Condition()
        self.do_cvar = True
        sel_mock = MagicMock()

        def sel_patch(rsrcs, wsrcs, esrcs, wait):
            do_cvar = self.do_cvar
            sel_mock(rsrcs, wsrcs, esrcs, wait)
            if do_cvar:
                with cvar:
                    cvar.wait()
            return [], [], []

        select_patch = patch.object(
            retrythread, 'select', new=sel_patch)
        select_patch.start()
        self.addCleanup(select_patch.stop)

        rthr = RetryThread()
        rthr.addRetryTime(20)
        self.wait_for(lambda: sel_mock.call_count == 1)
        del rthr
        self.do_cvar = False
        with cvar:
            cvar.notify()

        sel_mock.assert_called_with(ANY, [], ANY, RetryThread.max_select_wait)
