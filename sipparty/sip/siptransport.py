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
from sipparty.transport import (Transport, SockTypeFromName)
from sipparty.parse import ParseError
from message import Message
from components import Host
from transform import (TransformKeys,)
import prot

log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")
prot_log.setLevel(logging.INFO)
bytes = six.binary_type
itervalues = six.itervalues


class SIPTransport(Transport):
    """SIP specific subclass of Transport."""

    #
    # =================== CLASS INTERFACE =====================================
    #
    DefaultPort = 5060

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    messageConsumer = DerivedProperty("_sptr_messageConsumer")
    provisionalDialogs = DerivedProperty("_sptr_provisionalDialogs")
    establishedDialogs = DerivedProperty("_sptr_establishedDialogs")

    def __init__(self):
        if self.singletonInited:
            return
        super(SIPTransport, self).__init__()
        self._sptr_messageConsumer = None
        self._sptr_messages = []
        self._sptr_provisionalDialogs = {}
        self._sptr_establishedDialogs = {}
        # Dialog handler is keyed by AOR.
        self._sptr_dialogHandlers = {}
        # Dialogs are keyed by dialogID
        self._sptr_dialogs = WeakValueDictionary()

        self.byteConsumer = self.sipByteConsumer

    def addDialogHandlerForAOR(self, aor, handler):
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

        log.debug("Remove handler for AOR %r", aor)
        del hdlrs[aor]

    def sendMessage(self, msg, toAddr, fromAddr=None):
        log.debug("Send message %r -> %r type %s", fromAddr, toAddr)

        toAddr = self.fixTargetAddress(toAddr)
        fromAddr = self.fixTargetAddress(fromAddr)

        sockType = SockTypeFromName(msg.viaheader.transport)

        log.debug(
            "Normalized addresses: %r -> %r type", fromAddr, toAddr, sockType)

        super(SIPTransport, self).sendMessage(
            bytes(msg), toAddr, sockType=sockType, fromAddr=fromAddr)

    def fixTargetAddress(self, addr):
        if addr is None:
            return (None, 0)

        if isinstance(addr, Host):
            return self.resolveHost(addr.address, addr.port)

        if isinstance(addr, bytes):
            return self.resolveHost(addr)

        if addr[1] is None:
            return (addr[0], self.DefaultPort)

        return addr

    def sipByteConsumer(self, lAddr, rAddr, data):
        log.debug(
            "SIPTransport attempting to consume %d bytes.", len(data))

        # SIP messages always have \r\n\r\n after the headers and before any
        # bodies.
        eoleol = b'\r\n\r\n'

        eoleol_index = data.find(eoleol)
        if eoleol_index == -1:
            # No possibility of a full message yet.
            log.debug("Data not a full SIP message.")
            return 0

        # We've probably got a full message, so parse it.
        log.debug("Full message")
        try:
            msg = Message.Parse(data)
            log.info("Message parsed.")
        except ParseError as pe:
            log.error("Parse errror %s parsing message.", pe)
            return 0

        try:
            self.consumeMessage(msg)
        except Exception as exc:
            log.error(
                "Consuming %r message raised exception: %s" % (msg.type, exc))
        return msg.parsedBytes

    def consumeMessage(self, msg):
        self._sptr_messages.append(msg)

        if not hasattr(msg.FromHeader.parameters, "tag"):
            log.debug("FromHeader: %r", msg.FromHeader)
            log.info("Message with no from tag is discarded.")
            return
        if (not hasattr(msg, "Call_IDHeader") or
                len(msg.Call_IdHeader.value) == 0):
            log.debug("Call-ID: %r", msg.Call_IDHeader)
            log.info("Message with no Call-ID is discarded.")
            return

        if not hasattr(msg.ToHeader.parameters, "tag"):
            log.debug("Dialog creating message")
            self.consumeDialogCreatingMessage(msg)
        else:
            log.debug("In dialog message")
            self.consumeInDialogMessage(msg)

    def consumeDialogCreatingMessage(self, msg):
        toAOR = msg.ToHeader.field.value.uri.aor
        hdlrs = self._sptr_dialogHandlers

        log.debug("Is %r in %r?", toAOR, hdlrs)
        if toAOR not in hdlrs:
            log.info("Message for unregistered AOR %r discarded.", toAOR)
            return

        hdlrs[toAOR](msg)

    def consumeInDialogMessage(self, msg):
        toAOR = msg.ToHeader.field.value.uri.aor
        estDs = self.establishedDialogs

        if msg.isresponse():
            log.debug("Message is response")
            did = prot.EstablishedDialogID(
                msg.Call_IDHeader.value, msg.FromHeader.parameters.tag.value,
                msg.ToHeader.parameters.tag.value)
        else:
            log.debug("Message is request")
            did = prot.EstablishedDialogID(
                msg.Call_IDHeader.value, msg.ToHeader.parameters.tag.value,
                msg.FromHeader.parameters.tag.value)

        log.detail("Is established dialog %r in %r?", did, estDs)
        if did in estDs:
            log.debug("Found established dialog for %r", did)
            return estDs[did].receiveMessage(msg)

        pdid = prot.ProvisionalDialogIDFromEstablishedID(did)
        provDs = self.provisionalDialogs
        log.detail("Is provisional dialog %r in %r?", pdid, provDs)
        if pdid in provDs:
            log.debug("Found provisional dialog for %r", pdid)
            return provDs[pdid].receiveMessage(msg)

        log.warning(
            "Unable to find a dialog for message with dialog ID %r", did)
        log.detail("  Current provisional dialogs: %r", provDs)
        log.detail("  Current establishedDialogs dialogs: %r", estDs)
        return

    def updateDialogGrouping(self, dlg):
        log.detail("Update grouping for dlg %r", dlg)
        pds = self.provisionalDialogs
        eds = self.establishedDialogs
        pdid = dlg.provisionalDialogID
        if hasattr(dlg, "dialogID"):
            log.debug("Dialog is established.")
            did = dlg.dialogID
            if pdid in pds:
                log.debug("  Dialog was provisional.")
                del pds[pdid]
            if did not in eds:
                log.debug("  Dialog was not yet established.")
                eds[did] = dlg

        else:
            log.debug("Dialog is not established.")
            if pdid not in pds:
                log.debug("  Dialog is new.")
                pds[pdid] = dlg

    def removeDialog(self, dlg):
        pdid = dlg.provisionalDialogID
        pdids = self.provisionalDialogs
        if pdid in pdids:
            del pdids[pdid]

        try:
            did = dlg.dialogID
            eds = tp.establishedDialogs
            if did in eds:
                del eds[did]
        except AttributeError:
            pass

    #
    # =================== MAGIC METHODS =======================================
    #
    def __new__(cls, *args, **kwargs):
        if "singleton" not in kwargs:
            kwargs["singleton"] = "SIPTransport"
        inst = super(SIPTransport, cls).__new__(cls, *args, **kwargs)
        if not hasattr(SIPTransport, "inst"):
            SIPTransport.inst = inst
        assert SIPTransport.inst is inst, (SIPTransport.inst, inst)
        return inst

    #
    # =================== INTERNAL METHODS ====================================
    #
