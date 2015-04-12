"""ttransport.py

Unit tests for the transport code.

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
import time
import logging
import unittest
import retrythread
import fsm
import transport

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class TestFSM(unittest.TestCase):

    def wait_for(self, func, timeout=2):
        assert timeout > 0.05
        now = time.clock()
        until = now + timeout
        while time.clock() < until:
            if func():
                break
            time.sleep(0.01)
        else:
            self.assertTrue(0, "Timed out waiting for %r" % func)

    def clock(self):
        return self._clock

    def setUp(self):
        self._clock = 0
        fsm.Timer.Clock = self.clock
        retrythread.RetryThread.Clock = self.clock
        self.retry = 0
        self.cleanup = 0

    def testSimpleTransport(self):

        t1 = transport.TransportFSM()
        t1.connect()
        self.assertEqual(t1.state, t1.States.error)
        t1.reset()
        self.assertEqual(t1.state, t1.States.disconnected)

        t1.family = socket.AF_INET
        t1.type = socket.SOCK_STREAM
        t1.listen()
        self.assertEqual(t1.state, t1.States.listening)
        t1.hit(t1.Inputs.error, "user cancelled")
        self.wait_for(lambda: t1.state == t1.States.error)
        t1.reset()
        log.debug("Done.")

if __name__ == "__main__":
    sys.exit(unittest.main())
