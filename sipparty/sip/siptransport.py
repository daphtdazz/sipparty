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
import logging
from six import (binary_type as bytes)
from socket import (AF_INET, SOCK_DGRAM)
import sys
from weakref import (WeakValueDictionary)
from ..parse import ParseError
from ..transport import (
    IsValidTransportName, Transport, SockTypeFromName,
    UnregisteredPortGenerator)
from ..util import (abytes, DerivedProperty, Singleton, WeakMethod)
from . import prot
from .components import Host
from .message import Message

log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")
prot_log.setLevel(logging.INFO)


class SIPTransport(Transport):
    """SIPTransport."""

    #
    # =================== CLASS INTERFACE =====================================
    #
    DefaultPort = 5060
    DefaultType = SOCK_DGRAM

    @classmethod
    def port_generator(cls):
        yield 5060
        for port in UnregisteredPortGenerator():
            yield port

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    messageConsumer = DerivedProperty("_sptr_messageConsumer")

    # Do not iterate over these dictionaries, as they are weak value
    # dictionaries whose values may disappear at any time.
    provisionalDialogs = DerivedProperty("_sptr_provisionalDialogs")
    establishedDialogs = DerivedProperty("_sptr_establishedDialogs")

    def __init__(self):
        super(SIPTransport, self).__init__()
        self._sptr_messageConsumer = None
        self._sptr_messages = []
        self._sptr_provisionalDialogs = WeakValueDictionary()
        self._sptr_establishedDialogs = WeakValueDictionary()
        # Dialog handler is keyed by AOR.
        self._sptr_dialogHandlers = {}

    def listen_for_me(self, **kwargs):

        for val, default in (
                ('sock_type', self.DefaultType),
                ('port', self.DefaultPort)):
            if val not in kwargs or kwargs[val] is None:
                kwargs[val] = default
        return super(
            SIPTransport, self).listen_for_me(
                WeakMethod(self, 'sipByteConsumer'), **kwargs)

    def addDialogHandlerForAOR(self, aor, handler):
        """Register a handler to call """

        hdlrs = self._sptr_dialogHandlers
        if aor in hdlrs:
            raise KeyError(
                "Handler already registered for AOR %r" % bytes(aor))

        log.debug("Adding handler %r for AOR %r", handler, aor)
        hdlrs[aor] = handler

    def removeDialogHandlerForAOR(self, aor):

        hdlrs = self._sptr_dialogHandlers
        if aor not in hdlrs:
            raise KeyError(
                "AOR handler not registered for AOR %r" % bytes(aor))

        log.debug("Remove handler for AOR %r", aor)
        del hdlrs[aor]

    def sendMessage(self, msg, name, port):
        log.debug("Send message -> %r type %s", (name, port), msg.type)

        if not IsValidTransportName(name):
            raise TypeError(
                'remote_name %r is not a valid transport name (special name '
                'or string)' % name)

        sock_type = SockTypeFromName(msg.viaheader.transport)

        sp = super(SIPTransport, self).get_send_from_address(
            sock_type=sock_type, remote_name=name,
            remote_port=port,
            data_callback=WeakMethod(self, 'sipByteConsumer'))

        vh = msg.viaheader
        if not vh.address:
            vh.address = abytes(sp.local_address.name)

        if not vh.port:
            vh.port = sp.local_address.port
        sp.send(bytes(msg))

    def fixTargetAddress(self, addr):
        if addr is None:
            return (None, 0)

        if isinstance(addr, Host):
            return self.resolve_host(addr.address, addr.port)

        if isinstance(addr, bytes):
            return self.resolve_host(addr)

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
        except Exception:
            log.exception(
                "Consuming %r message raised exception.", msg)
            #sys.exc_clear()

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

        hdlr = hdlrs[toAOR]
        hdlr(msg)

    def consumeInDialogMessage(self, msg):
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

        # Couldn't find an established dialog, so perhaps this is the
        # establishing response for a provisional dialog we started before.
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
            eds = self.establishedDialogs
            if did in eds:
                del eds[did]
        except AttributeError:
            pass
