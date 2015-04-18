"""siptransport.py

Specializes the transport layer for SIP.

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
import six
import weakref
import logging
import _util
import prot
import transport
import message

log = logging.getLogger(__name__)


class SipTransportFSM(transport.TransportFSM):

    #
    # =================== CLASS INTERFACE ====================================
    #

    # These are cumulative with the super classes'.
    States = _util.Enum(())

    @classmethod
    def AddClassTransitions(cls):
        transport.TransportFSM.AddClassTransitions()

    #
    # =================== INSTANCE INTERFACE =================================
    #
    def __init__(self):
        super(SipTransportFSM, self).__init__(self)

        # Use a weak reference to set up our consuming method as else we will
        # retain ourselves.
        weak_self = weakref.ref(self)

        def siptfsm_consumer(data):
            self = weak_self()
            if self is None:
                return 0
            return self._tsfsm_consumeBytes(data)

        self.byteConsumer = siptfsm_consumer

    def sendMessage(self, message):
        pass

    #
    # =================== INTERNAL ===========================================
    #
    def _tsfsm_consumeBytes(self, data):
        eoleol = bytearray(prot.EOL * 2)
