"""Specializes the transport layer for SIP.

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
from abc import ABCMeta, abstractmethod
import logging
from six import (add_metaclass, binary_type as bytes)
from socket import SOCK_DGRAM
from ..classmaker import classbuilder
from ..parse import ParseError
from ..transport import (
    IsValidTransportName, Transport, SockTypeFromName,
    UnregisteredPortGenerator)
from ..util import (abytes, DerivedProperty, profile, WeakMethod)
from . import prot
from .components import AOR, Host
from .message import Message
from .transaction import TransactionManager, TransactionTransport
from . import Incomplete

log = logging.getLogger(__name__)


@add_metaclass(ABCMeta)
class AORHandler(object):

    @abstractmethod
    def new_dialog_from_request(self, req):
        """Handle a dialog creating request.

        :raises Exception:
            Any exception raised is logged at error level and the
        :returns: A Dialog instance.
        """
        raise NotImplemented


@classbuilder(bases=(Transport, TransactionTransport))
class SIPTransport:
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
        self._sptr_provisionalDialogs = {}
        self._sptr_establishedDialogs = {}

        # Dialog handler is keyed by AOR. This can't be a WeakValueDictionary
        # because generally methods are transient objects which will get
        # released if we don't store strong references to them. Therefore if
        # you want a weak reference, use WeakMethod.
        self._sptr_dialogHandlers = {}
        self.transaction_manager = TransactionManager(self)

    def listen_for_me(self, **kwargs):

        for val, default in (
                ('sock_type', self.DefaultType),
                ('port', self.DefaultPort)):
            if val not in kwargs or kwargs[val] is None:
                kwargs[val] = default
        return super(
            SIPTransport, self).listen_for_me(
                WeakMethod(self, 'sipByteConsumer'), **kwargs)

    #
    # =================== AOR MANAGER INTERFACE ===============================
    #
    def addDialogHandlerForAOR(self, aor, handler):
        """Register a handler to call."""
        if not isinstance(handler, AORHandler):
            raise TypeError('%s instance is not of type AORHandler' % (
                type(handler).__name__,))

        if not isinstance(aor, AOR):
            raise TypeError('%s instance is not an AOR' % type(aor).__name__)

        hdlrs = self._sptr_dialogHandlers
        aor_bytes = bytes(aor)
        if aor_bytes in hdlrs:
            raise KeyError(
                "Handler already registered for AOR %r" % aor_bytes)

        log.debug("Adding handler %r for AOR %r", handler, aor_bytes)
        hdlrs[aor_bytes] = handler

        if log.getEffectiveLevel() <= logging.DETAIL:
            log.detail('All aors to handle now: %s', ', '.join(
                [str(key) for key in hdlrs.keys()]))

    def removeDialogHandlerForAOR(self, aor):
        hdlrs = self._sptr_dialogHandlers
        aor_bytes = bytes(aor)
        if aor_bytes not in hdlrs:
            raise KeyError(
                "AOR handler not registered for AOR %r" % aor_bytes)

        log.debug("Remove handler for AOR %r", aor_bytes)
        del hdlrs[aor_bytes]

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

    @profile
    def send_message_with_transaction(
            self, msg, transaction_user, remote_name=None, remote_port=None,
            **kwargs):
        """Send a message reliabily using an appropriate transaction."""
        log.debug('Find the transaction')

        kwargs.update({
            k: v
            for k, v in (
                ('remote_name', remote_name), ('remote_port', remote_port)
            ) if v is not None
        })
        trns = self.transaction_manager.transaction_for_outbound_message(
            msg, transaction_user=transaction_user)
        trns.handle_outbound_message(msg, **kwargs)

    #
    # =================== TRANSPORT SENDER INTERFACE ==========================
    #
    def send_message(self, msg, name, port):
        log.debug("Send message -> %r type %s", (name, port), msg.type)

        if not IsValidTransportName(name):
            raise TypeError(
                'remote_name %r is not a valid transport name (special name '
                'or string)' % name)

        sock_type = SockTypeFromName(msg.viaheader.transport)

        sp = super(SIPTransport, self)
        sprxy = super(SIPTransport, self).get_send_from_address(
            sock_type=sock_type, remote_name=name,
            remote_port=port,
            data_callback=WeakMethod(self, 'sipByteConsumer'))

        ch = msg.contactheader
        if not ch.address:
            ch.address = abytes(sprxy.local_address.name)

        if not ch.port:
            ch.port = sprxy.local_address.port

        try:
            sprxy.send(bytes(msg))
        except Incomplete:
            sp.release_listen_address(sprxy.local_address)
            raise

        return sprxy.local_address

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

    def sipByteConsumer(self, local_addr, remote_addr, data):
        log.debug(
            "SIPTransport attempting to consume %d bytes.", len(data))

        # SIP messages always have \r\n\r\n after the headers and before any
        # bodies.
        eoleol = b'\r\n\r\n'

        eoleol_index = data.find(eoleol)
        if eoleol_index == -1:
            # No possibility of a full message yet.
            log.warning("Data not a full SIP message.")
            return 0

        # We've probably got a full message, so parse it.
        log.debug("Full message")
        try:
            msg = Message.Parse(data)
            log.debug("Message parsed.")
        except ParseError as pe:
            log.error("Parse errror %s parsing message.", pe)
            return 0
        try:
            self.consumeMessage(msg)
        except Exception:
            log.exception(
                "Consuming %s message raised exception.", msg.type)

        return msg.parsedBytes

    def consumeMessage(self, msg):
        self._sptr_messages.append(msg)

        if not hasattr(msg.FromHeader.parameters, "tag"):
            log.debug("FromHeader: %r", msg.FromHeader)
            log.warning("Message with no From: tag is discarded.")
            return

        if (not hasattr(msg, "Call_IDHeader") or
                len(msg.Call_IdHeader.value) == 0):
            log.debug("Call-ID: %r", msg.Call_IDHeader)
            log.warning("Message with no Call-ID is discarded.")
            return

        # See if we have a transaction
        trns = self.transaction_manager.transaction_for_inbound_message(msg)
        assert trns is not None

        if trns.state != trns.States.Initial:
            log.debug('Message for current transaction.')
            trns.consume_message(msg)
            return

        if not hasattr(msg.ToHeader.parameters, "tag"):
            log.debug("Dialog creating message")
            self.consumeDialogCreatingMessage(msg, trns)
            return

        log.debug("In dialog message")
        self.consumeInDialogMessage(msg, trns)

    def consumeDialogCreatingMessage(self, msg, trns):
        toAOR = msg.ToHeader.field.value.uri.aor
        hdlrs = self._sptr_dialogHandlers

        log.debug("Find handler for %r", toAOR)
        to_aor_bytes = bytes(toAOR)
        if to_aor_bytes not in hdlrs:
            log.warning(
                "Message for unregistered AOR %r discarded.", to_aor_bytes)
            return

        hdlr = hdlrs[to_aor_bytes]

        dlg = hdlr.new_dialog_from_request(msg)
        if dlg is None:
            log.warning(
                'Dropped dialog creating %s message as not wanted by AOR '
                'handler', msg.type)
            return

        trns.transaction_user = dlg
        trns.consume_message(msg)
        self.updateDialogGrouping(dlg)

    def consumeInDialogMessage(self, msg, trns):
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
        dlg = estDs.get(did)
        if dlg is not None:
            log.debug("Found established dialog for %r", did)
            trns.transaction_user = dlg
            trns.consume_message(msg)
            return

        # Couldn't find an established dialog, so perhaps this is the
        # establishing response for a provisional dialog we started before.
        pdid = prot.ProvisionalDialogIDFromEstablishedID(did)
        provDs = self.provisionalDialogs
        log.detail("Is provisional dialog %r in %r?", pdid, provDs)
        dlg = provDs.get(pdid)
        if dlg is not None:
            log.debug("Found provisional dialog for %r", pdid)
            trns.transaction_user = dlg
            trns.consume_message(msg)
            return

        raise RuntimeError(
            'Unable to find a dialog for message with dialog ID %r, '
            'provisional dialogs: %r, established dialogs: %r' % (
                did, provDs, estDs))
