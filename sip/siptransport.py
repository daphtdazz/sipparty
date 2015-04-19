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
    States = _util.Enum(
        ("sendingreq", "waitingrsp"))

    @classmethod
    def AddClassTransitions(cls):
        log.debug("STFSM's states: %r", cls.States)
        super(cls, cls).AddClassTransitions()

    #
    # =================== INSTANCE INTERFACE =================================
    #
    def __init__(self):
        super(SipTransportFSM, self).__init__()

        self._tsipfsm_messages = []

        # Use a weak reference to set up our consuming method as else we will
        # retain ourselves.
        weak_self = weakref.ref(self)

        def siptfsm_consumer(data):
            strong_self = weak_self()
            if strong_self is None:
                return 0
            return strong_self._tsfsm_consumeBytes(data)

        self.byteConsumer = siptfsm_consumer

    messages = _util.DerivedProperty("_tsipfsm_messages")
    messageConsumer = _util.DerivedProperty(
        "_tsipfsm_byteConsumer",
        lambda val: isinstance(val, collections.Callable))

    def sendMessage(self, message):
        self.hit(self.Inputs.send, six.binary_type(message))

    #
    # =================== INTERNAL ===========================================
    #
    def _tsfsm_consumeBytes(self, data):
        log.debug(
            "SipTransportFSM attempting to consume %d bytes.", len(data))
        log.debug("%r", data)

        # SIP messages always have \r\n\r\n after the headers and before any
        # bodies.
        eoleol = prot.EOL * 2

        eoleol_index = data.find(eoleol)
        if eoleol_index == -1:
            # No possibility of a full message yet.
            log.debug("Data not a full SIP message.")
            return 0

        # We've got a full message, so parse it.
        newmessage = message.Message.Parse(data)
        message_end = eoleol_index + len(eoleol)

        # !!! Look at content length header / stream type (if available) and
        # use that to burn the remaining data.

        self.messages.append(newmessage)

        return message_end
