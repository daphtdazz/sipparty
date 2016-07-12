"""testfsmtimer.py

Unit tests for the SIP FSM timer.

Copyright 2016 David Park

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
from __future__ import print_function

import logging
from threading import Semaphore, Thread
from ..fsm import fsmtimer
from ..fsm.fsmtimer import Timer
from ..util import WaitFor
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestFSMTimer(SIPPartyTestCase):

    Clock = MagicMock()

    def setUp(self):
        super(TestFSMTimer, self).setUp()
        self.timer_pops = 0
        self.sema = Semaphore()
        self.Clock.return_value = 0

    def timer_pop(self):
        self.timer_pops += 1
        self.sema.acquire()
        self.sema.release()

    @patch.object(fsmtimer, 'Clock', new=Clock)
    def test_window_expire_property(self):
        """Test that we can't move to expired state until we have expired!"""
        tm = Timer('test has_expired window', self.timer_pop, [0, 4])

        def check_expired():
            for ii in range(1000):
                self.assertFalse(tm.has_expired)
            self.sema.release()

        def check_timer():
            WaitFor(lambda: tm.was_started)
            for ii in range(1000):
                tm.check()

        self.Clock.return_value = 1
        td1, td2 = Thread(target=check_expired), Thread(target=check_timer)
        td1.start()
        td2.start()
        tm.start()
        td1.join()
        td2.join()
        self.sema.acquire()
        self.assertEqual(self.timer_pops, 1)
