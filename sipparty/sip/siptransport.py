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
import logging
import socket
from weakref import WeakValueDictionary

from sipparty.util import DerivedProperty
from sipparty.parse import ParseError
from sipparty.sip import Message
from transport import Transport
import prot

log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")
prot_log.setLevel(logging.INFO)
bytes = six.binary_type
itervalues = six.itervalues


class SIPTransport(Transport):
    """SIP specific subclass of Transport."""
    #
    # =================== INSTANCE INTERFACE ==================================
    #
    messageConsumer = DerivedProperty("_sptr_messageConsumer")

    def __init__(self):
        super(SIPTransport, self).__init__()
        self._sptr_messageConsumer = None
        self._sptr_messages = []
        # Dialog handler is keyed by AOR.
        self._sptr_dialogHandlers = {}
        self._sptr_dialogs = WeakValueDictionary()

        self.byteConsumer = self.sipByteConsumer

    def addDialogHandlerForAOR(self, handler, aor):
        """Register a handler to call """

        hdlrs = self._sptr_dialogHandlers
        if handler in hdlrs:
            raise KeyError(
                "Handler already registered for AOR %r" % bytes(aor))

        log.debug("Adding handler %r for AOR %r", handler, aor)
        hdlrs[aor] = handler

    def removeDialogHandlerForAOR(self, aor):

        hdlrs = self._sptr_dialogHandlers
        if handler not in hdlrs:
            raise KeyError(
                "AOR handler not registered for AOR %r" % bytes(aor))

        del hdlrs[aor]

    def sendMessage(self, msg, toAddr, sockType=None):
        super(SIPTransport, self).sendMessage(
            bytes(msg), toAddr, sockType=sockType)

    def sipByteConsumer(self, data):
        log.debug(
            "SIPTransport attempting to consume %d bytes.", len(data))

        # SIP messages always have \r\n\r\n after the headers and before any
        # bodies.
        eoleol = prot.EOL * 2

        eoleol_index = data.find(eoleol)
        if eoleol_index == -1:
            # No possibility of a full message yet.
            log.debug("Data not a full SIP message.")
            return 0

        # We're going to consume the whole message, one way or another.
        mlen = eoleol_index + len(eoleol)
        self.consumeMessageData(data[:mlen])
        return mlen

    def consumeMessageData(self, data):
        # We've got a full message, so parse it.
        log.debug("Full message")
        try:
            msg = Message.Parse(data)
        except ParseError as pe:
            return

        self.consumeMessage(msg)

    def consumeMessage(self, msg):
        self._sptr_messages.append(msg)

        if not hasattr(msg.FromHeader.parameters, "tag"):
            log.debug("FromHeader: %r", msg.FromHeader)
            log.info("Message with no from tag is discarded.")
            return
        if (
                not hasattr(msg, "Call_IDHeader") or
                len(msg.Call_IdHeader.field) == 0):
            log.debug("Call-ID: %r", msg.Call_IDHeader)
            log.info("Message with no Call-ID is discarded.")
            return

        if not hasattr(msg.ToHeader.parameters, "tag"):
            self.consumeDialogCreatingMessage(msg)
        else:
            self.consumeInDialogMessage(msg)

    def consumeDialogCreatingMessage(self, msg):
        toAOR = msg.ToHeader.field.value.uri.aor
        hdlrs = self._sptr_dialogHandlers

        if toAOR not in hdlrs:
            log.info("Message for unregistered AOR %r discarded.", toAOR)
            return

        hdlrs[toAOR](msg)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        log.debug("Deleting SIPTransport")
        sp = super(SIPTransport, self)
        if hasattr(sp, "__del__"):
            sp.__del__()

    #
    # =================== INTERNAL METHODS ====================================
    #
