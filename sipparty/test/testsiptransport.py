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

from sipparty.sip import (components, message, siptransport, transform)


class TestSIPTransport(unittest.TestCase):

    def wait_for(self, func, timeout=2):
        assert timeout > 0.05
        now = timeit.default_timer()
        until = now + timeout
        while timeit.default_timer() < until:
            if func():
                break
            time.sleep(0.01)
        else:
            self.assertTrue(0, "Timed out waiting for %r" % func)

    def testConnectedTidyUp(self):
        self.subTestBasicSIPTransport(1)

    def testBasicSIPTransport(self):
        self.subTestBasicSIPTransport(0)

    def subTestBasicSIPTransport(self, finish_point):
        global t1
        t1 = None
        def AcceptConsumer(tp):
            global t1
            t1 = tp

        S = siptransport.SipTransport.States
        I = siptransport.SipTransport.Inputs

        l1 = siptransport.SipListenTransport()
        l1.acceptConsumer = AcceptConsumer
        t2 = siptransport.SipTransport()

        l1.listen()
        log.debug("t1.localAddress: %r", l1.localAddress)

        t2.hit(I.attemptConnect, l1.localAddress)

        self.wait_for(lambda: t2.state == S.connected)
        self.wait_for(lambda: t1 is not None)
        self.wait_for(lambda: t1.state == S.connected)

        if finish_point == 1:
            return

        inv = message.Message.invite()
        inv.fromHeader.uri.aor = components.AOR(
            "alice", "atlanta.com")
        inv.toHeader.field.value.uri.aor = components.AOR("bob", "biloxi.com")
        inv.contactHeader.field.value.uri.aor.username = "alice"
        inv.contactHeader.field.value.uri.aor.host = t1.localAddressHost

        t1.send(six.binary_type(inv))

        self.wait_for(lambda: len(t2.messages) > 0)

        rx = t2.messages.pop()
        resp = message.Response(200)
        log.debug("t1 state: %r, t2 state: %r.", t1.state, t2.state)
        rx.applyTransform(resp, transform.default[rx.type][200])

        t2.send(six.binary_type(resp))

        self.wait_for(lambda: len(t1.messages) > 0)

        resp = t1.messages.pop()
        self.assertEquals(resp.startline.code, 200)

        self.assertEqual(inv.fromHeader.field.parameters["tag"],
                         resp.fromHeader.field.parameters["tag"])

        t1.hit(I.disconnect)

if __name__ == "__main__":
    unittest.main()
