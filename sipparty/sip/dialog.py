"""dialog.py

Implements a `Dialog` object.

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
import re
import logging
import abc

from sipparty import (vb, util, fsm)
from sipparty.fsm import (FSM,)
import header
from param import TagParam

log = logging.getLogger(__name__)
bytes = six.binary_type

States = util.Enum((
    fsm.InitialStateKey, "InitiatingDialog", "InDialog", "TerminatingDialog",
    "SuccessCompletion", "ErrorCompletion"))
Inputs = util.Enum(("initiate", "terminate"))


class Dialog(fsm.FSM, vb.ValueBinder):
    """`Dialog` class has a slightly wider scope than a strict SIP dialog, to
    include one-off request response pairs (e.g. OPTIONS) as well as long-lived
    stateful relationships (Calls, Registrations etc.).

    A `Dialog` instance may not be reused.

    See https://tools.ietf.org/html/rfc3261#section-12 for the RFC description
    of dialogs. It says:

        A dialog is identified at each UA with a dialog ID ... Call-ID ...
        local tag ... remote tag.
    """

    #
    # =================== CLASS INTERFACE =====================================
    #
    vb_bindings = [
    ]
    vb_dependencies = [
        ("transport", ["sendMessage"])
    ]

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    requests = util.DerivedProperty(
        "_dlg_requests", lambda x: isinstance(x, list))
    request = util.FirstListItemProxy("requests")
    localTag = util.DerivedProperty("_dlg_localTag")
    remoteTag = util.DerivedProperty(
        "_dlg_remoteTag", lambda x: isinstance(x, TagParam))
    callIDHeader = util.DerivedProperty(
        "_dlg_callIDHeader", lambda x: isinstance(x, header.Header.call_id))
    transport = util.DerivedProperty("_dlg_transport")

    @property
    def provisionalDialogID(self):
        return (self._dlg_callIDHeader.field, self.localTag.value)

    @property
    def dialogID(self):
        rt = self.remoteTag
        if rt is None:
            raise AttributeError(
                "%r instance has no remote tag so is not yet in a dialog so "
                "does not have a dialogID." % (self.__class__.__name__,))
        return (self._dlg_callIDHeader.field, self.localTag.value, rt)

    def __init__(self, callIDHeader=None, callIDHost=None, remoteTag=None):
        super(Dialog, self).__init__()
        self._dlg_currentTransaction = None
        self._dlg_requests = []
        self._dlg_localTag = TagParam()
        self._dlg_remoteTag = None
        self._dlg_transport = None
        if callIDHeader is None:
            callIDHeader = header.Header.call_id()
            if callIDHost is not None:
                callIDHeader.host = callIDHost
        else:
            assert callIDHost is None, (
                "Can't pass both callIDHeader and callIDHost")

        self.callIDHeader = callIDHeader

    def initiate(self, *args, **kwargs):
        log.debug("Initiating dialog...")
        self.hit(Inputs.initiate, *args, **kwargs)

    def terminate(self, *args, **kwargs):
        self.hit(Inputs.terminate, *args, **kwargs)

    def sendRequest(self, request):
        # TODO: write
        #
        # Transaction or not?
        #
        # Transform:
        request.FromHeader.parameters.tag = self.localTag
        request.ToHeader.parameters.tag = self.remoteTag
        request.Call_IDHeader = self.callIDHeader

        log.debug("sendRequest %r", request)

        ht = request.ToHeader.field.uri.aor.host

        self.transport.sendMessage(request, ht)

    def sendResponse(self, response):
        request.FromHeader.parameters.tag = self.remoteTag
        request.ToHeader.parameters.tag = self.localTag
        assert 0

    #
    # =================== DELEGATE METHODS ====================================
    #
    def messageConsumer(self, message):
        log.debug("Received a %r message.", message.type)
        tt = None
        cleaor = None
        if self.theirTag is None:
            if message.isrequest():
                tt = message.FromHeader.field.parameters.tag
                cleaor = message.FromHeader.field.value.uri.aor
            else:
                tt = message.ToHeader.field.parameters.tag
                cleaor = message.ToHeader.field.value.uri.aor
            self.theirTag = tt
            self.calleeAOR = cleaor
        log.debug("Their tag: %r", tt)
        log.debug("Their AOR: %r", cleaor)

        try:
            self.scenario.hit(message.type, message)
        except fsm.UnexpectedInput as exc:
            # fsm has already logged the error. We just carry on.
            pass

    def _pt_send(self, message_type, callee=None, contactAddress=None):
        log.debug("Send message of type %r to %r.", message_type, callee)

        tp = self._pt_transport

        if self.myTag is None:
            self.myTag = TagParam()

        if callee is not None:
            # Callee can be overridden with various different types of object.
            if isinstance(callee, components.AOR):
                calleeAOR = callee
            elif hasattr(callee, "aor"):
                calleeAOR = callee.aor
            else:
                calleeAOR = components.AOR.Parse(callee)
            log.debug("calleeAOR: %r", calleeAOR)
            self.calleeAOR = calleeAOR
        else:
            if self.calleeAOR is None:
                self._pt_stateError(
                    "Send message for %r instance (aor: %s) passed no "
                    "aor." % (
                        self.__class__.__name__, self.aor))
            calleeAOR = self.calleeAOR

        if contactAddress is None:
            if callee is not None and hasattr(callee, "localAddress"):
                # Looks like we've been passed another sip party to connect
                # to.
                contactAddress = callee.localAddress
            elif tp.state == tp.States.connected:
                # We're already connected, so use the transport's remote
                # address.
                contactAddress = tp.remoteAddress
            else:
                # Otherwise try and use the address from the AOR.
                contactAddress = calleeAOR.host.addrTuple()

        if not isinstance(calleeAOR, components.AOR):
            # Perhaps we can make an AOR out of it?
            try:
                calleeAOR = components.AOR.Parse(calleeAOR)
                log.debug("Callee: %r, host: %r.", calleeAOR, calleeAOR.host)
            except TypeError, parse.ParseError:
                raise ValueError(
                    "Message recipient is not an AOR: %r." % callee)

        self.calleeAOR = calleeAOR
        log.debug("%r", self.calleeAOR)

        log.info("Connecting to address %r.", contactAddress)
        self._pt_connectTransport(contactAddress)

        msg = getattr(Message, message_type)()

        # Hook it onto the outbound message. This does all the work of setting
        # attributes from ourself as per our bindings.
        self._pt_outboundRequest = msg

        log.debug("%r", self._pt_outboundRequest)

        try:
            tp.send(bytes(msg))
        finally:
            # Important to delete the message because it is bound to our
            # properties, and we will have binding conflicts with later
            # messages if it is not released now.
            log.debug("Delete outbound message.")
            self._pt_outboundRequest = None
            self._pt_lastRequest = msg

    #
    # =================== MAGIC METHODS =======================================
    #
    def __getattr__(self, attr):

        if Dialog.sendRequestRE.match(attr):
            return util.WeakMethod(
                self, "sendRequest", attr.replace("sendRequest", "", 1))

        try:
            return super(Dialog, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "%r instance has no attribute %r." % (
                    self.__class__.__name__, attr))
    sendRequestRE = re.compile("sendRequest", re.IGNORECASE)

    #
    # =================== INTERNAL METHODS ====================================
    #
    def _pt_reply(self, message_type, request):
        log.debug("Reply to %r with %r.", request.type, message_type)

        if self.myTag is None:
            self.myTag = TagParam()

        if re.match("\d+$", message_type):
            message_type = int(message_type)
            msg = message.Response(code=message_type)
        else:
            msg = getattr(message.Message, message_type)()

        tform = self._pt_transformForReply(request.type, message_type)
        request.applyTransform(msg, tform, request=self._pt_lastRequest)

        self._pt_outboundResponse = msg

        try:
            self._pt_transport.send(bytes(msg))
        finally:
            self._pt_outboundResponse = None
            del msg

    def _pt_stateError(self, message):
        self._pt_reset()
        raise UnexpectedState(message)

    def _pt_reset(self):
        self._pt_transport.disconnect()
        self._pt_resetScenario()
        del self._pt_lastRequest

    def _pt_connectTransport(self, remoteAddress):

        tp = self._pt_transport
        if tp.state != tp.States.connected:
            tp.connect(remoteAddress)
            util.WaitFor(lambda: tp.state in (
                tp.States.connected,
                tp.States.error), 10.0)

        assert tp.remoteAddress[:2] == remoteAddress[:2], (
            "%r != %r" % (tp.remoteAddress, remoteAddress))

        if tp.state == tp.States.error:
            self._pt_stateError(
                "Got an error attempting to connect to %r." % (
                    remoteAddress))
