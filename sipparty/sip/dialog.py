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
from copy import deepcopy
import logging
import numbers
import re
from .. import vb
from ..fsm import (AsyncFSM, InitialStateKey, UnexpectedInput)
from ..deepclass import DeepClass, dck
from ..parse import ParsedPropertyOfClass
from ..sdp import (sdpsyntax, SDPIncomplete)
from ..transport import IsValidPortNum
from ..util import (abytes, astr, Enum, WeakMethod)
from .transform import (Transform, TransformKeys)
from .components import URI
from .header import Call_IdHeader
from .request import Request
from .message import Message, MessageResponse
from .param import TagParam
from .body import Body
from . import prot

log = logging.getLogger(__name__)

States = Enum((
    InitialStateKey, "InitiatingDialog", "InDialog", "TerminatingDialog",
    "SuccessCompletion", "ErrorCompletion"))
Inputs = Enum(("initiate", "receiveRequest", "terminate"))

tfk = TransformKeys

AckTransforms = {
    200: {
        b"ACK": (
            (tfk.CopyFrom, "request", "FromHeader"),
            (tfk.CopyFrom, "request", "Call_IDHeader"),
            (tfk.CopyFrom, "request", "startline.uri"),
            (tfk.CopyFrom, "request", "viaheader"),
            (tfk.CopyFrom, 'request', 'ContactHeader'),
            (tfk.Copy, "startline.protocol",),
            (tfk.Copy, "ToHeader"),
        )
    }
}


class Dialog(
        DeepClass("_dlg_", {
            "fromURI": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "toURI": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "contactURI": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "remote_name": {},
            "remote_port": {dck.check: IsValidPortNum},
            "localTag": {},
            "remoteTag": {},
            "transport": {},
            "localSession": {},
            "remoteSession": {}}),
        AsyncFSM, vb.ValueBinder):
    """`Dialog` class has a slightly wider scope than a strict SIP dialog, to
    include one-off request response pairs (e.g. OPTIONS) as well as long-lived
    stateful relationships (Calls, Registrations etc.).

    A `Dialog` instance may not be reused.

    See https://tools.ietf.org/html/rfc3261#section-12 for the RFC description
    of dialogs. It says:

        A dialog is identified at each UA with a dialog ID [this is composed
        of] Call-ID ... local tag ... remote tag.

    """

    #
    # =================== CLASS INTERFACE =====================================
    #
    States = States
    Transforms = None

    #
    # =================== INSTANCE INTERFACE ==================================
    #

    @property
    def provisionalDialogID(self):
        return prot.ProvisionalDialogID(
            self._dlg_callIDHeader.value, self.localTag.value)

    @property
    def dialogID(self):
        rt = self.remoteTag
        if rt is None:
            raise AttributeError(
                "%r instance has no remote tag so is not yet in a dialog so "
                "does not have a dialogID." % (self.__class__.__name__,))
        return prot.EstablishedDialogID(
            self._dlg_callIDHeader.value, self.localTag.value, rt.value)

    def __init__(self, **kwargs):
        super(Dialog, self).__init__(**kwargs)

        self._dlg_callIDHeader = None
        self._dlg_localTag = TagParam()
        self._dlg_remoteTag = None
        self._dlg_requests = []

    def initiate(self, *args, **kwargs):
        log.debug("Initiating dialog...")
        self.hit(Inputs.initiate, *args, **kwargs)

    def terminate(self, *args, **kwargs):
        self.hit(Inputs.terminate, *args, **kwargs)

    def receiveMessage(self, msg):

        log.debug("Dialog receiving message")
        log.detail("%r", msg)
        mtype = msg.type

        if mtype in (200,):
            log.debug("ACKing %r message", mtype)
            self.ackMessage(msg)

        def RaiseBadInput(msg=b""):
            raise(UnexpectedInput(
                "%r instance fsm has no input for message type %r." % (
                    self.__class__.__name__, mtype)))

        if self._dlg_callIDHeader is None:
            self._dlg_callIDHeader = msg.Call_IdHeader

        if self.remoteTag is None:
            if msg.isresponse():
                log.debug("Message is a response")
                rtag = msg.ToHeader.parameters.tag
            else:
                log.debug("Message is a request")
                rtag = msg.FromHeader.parameters.tag
            log.debug("Learning remote tag: %r", rtag)
            self.remoteTag = rtag
            tp = self.transport
            if tp is not None:
                tp.updateDialogGrouping(self)

        if self.contactURI is None:
            cURI = msg.ContactHeader.uri
            log.debug("Learning contactURI: %r", cURI)
            self.contactURI = cURI

        if mtype in Request.types:
            input = "receiveRequest" + getattr(Request.types, mtype)
            return self.hit(input, msg)

        rcode = mtype
        if not isinstance(rcode, numbers.Integral):
            RaiseBadInput()

        while mtype >= 1:
            attr = "receiveResponse%d" % mtype
            if attr in self.Inputs:
                log.debug("Response input found: %d", mtype)
                return self.hit(attr, msg)

            mtype /= 10

        RaiseBadInput()

    def ackMessage(self, msg):

        ack = Message.ACK(autofillheaders=False)
        assert len(self._dlg_requests)

        mtype = msg.type
        if isinstance(mtype, str):
            mtype = abytes(mtype)
        Transform(
            AckTransforms, msg, mtype, ack, abytes(ack.type),
            request=self._dlg_requests[-1])

        self.transport.sendMessage(
            ack, self.remote_name, self.remote_port)

    def sendRequest(self, reqType, remote_name=None, remote_port=None):

        if self._dlg_callIDHeader is None:
            log.debug("First request, generate call ID header.")
            self._dlg_callIDHeader = Call_IdHeader()

        if remote_name is not None:
            log.debug("Learning remote address: %r", remote_name)
            self.remote_name = astr(remote_name)

        if remote_port is not None:
            log.debug("Learning remote port: %r", remote_port)
            self.remote_port = remote_port

        for reqdAttr in (
                "fromURI", "toURI", "contactURI", "remote_name",
                "transport"):
            attrVal = getattr(self, reqdAttr)
            if attrVal is None:
                raise ValueError(
                    "Attribute %r of %r instance required to send a request "
                    "is None." % (
                        reqdAttr, self.__class__.__name__))

        req = getattr(Message, reqType)()
        req.startline.uri = deepcopy(self.toURI)
        req.ToHeader.uri = deepcopy(self.toURI)

        req.FromHeader.field.value.uri = deepcopy(self.fromURI)
        req.ContactHeader.uri = deepcopy(self.contactURI)

        req.FromHeader.parameters.tag = deepcopy(self.localTag)
        req.ToHeader.parameters.tag = deepcopy(self.remoteTag)
        req.Call_IdHeader = deepcopy(self._dlg_callIDHeader)

        log.debug("send request of type %r", req.type)

        if req.type == req.types.invite:
            self.addLocalSessionSDP(req)

        if hasattr(self, "delegate"):
            dele = self.delegate
            if hasattr(dele, "configureOutboundMessage"):
                dele.configureOutboundMessage(req)

        tp = self.transport
        if tp is None:
            raise AttributeError(
                "%r instance has no transport attribute so cannot send a "
                "request." % (self.__class__.__name__,))

        try:
            tp.sendMessage(req, self.remote_name, self.remote_port)
        except prot.Incomplete:
            log.error("Incomplete message of type %s", req.type)
            raise

        req.unbindAll()
        self._dlg_requests.append(req)
        tp.updateDialogGrouping(self)

    def sendResponse(self, response, req):
        log.debug("Send response type %r.", response)

        resp = MessageResponse(response)
        self.configureResponse(resp, req)
        vh = req.viaheader
        self.transport.sendMessage(resp, astr(vh.address), vh.port)

    def configureResponse(self, resp, req):
        log.debug("Configure response starting with %r", resp)
        log.debug('Request was: %r', req)

        Transform(self.Transforms, req, req.type, resp, resp.type)

        log.debug('Transformed to %r', resp)

        if req.type == req.types.invite and resp.type == 200:
            self.addLocalSessionSDP(resp)

        resp.FromHeader.parameters.tag = self.remoteTag
        resp.ToHeader.parameters.tag = self.localTag

        if hasattr(self, "delegate"):
            dele = self.delegate
            if hasattr(dele, "configureOutboundMessage"):
                dele.configureOutboundMessage(resp)

        log.debug("Response now %r", resp)

    def hasTerminated(self):
        """Dialog is over. Remove it from the transport."""
        tp = self.transport
        if tp is not None:
            tp.removeDialog(self)

    #
    # =================== DELEGATE METHODS ====================================
    #

    #
    # =================== MAGIC METHODS =======================================
    #
    sendRequestRE = re.compile(
        "^sendRequest(%s)$" % "|".join(Request.types),
        re.IGNORECASE)
    sendResponseRE = re.compile("^sendResponse([0-9]+)$", re.IGNORECASE)

    def __getattr__(self, attr):

        mo = Dialog.sendRequestRE.match(attr)
        if mo:
            method = getattr(Request.types, mo.group(1))
            log.debug("Method is type %r", method)
            return WeakMethod(self, "sendRequest", static_args=(method,))

        mo = Dialog.sendResponseRE.match(attr)
        if mo:
            code = int(mo.group(1))
            while code < 100:
                code *= 100
            return WeakMethod(self, "sendResponse", static_args=(code,))

        try:
            log.detail("Attr %r matches nothing so far.", attr)
            return super(Dialog, self).__getattr__(attr)

        except AttributeError:
            raise AttributeError(
                "%r instance has no attribute %r." % (
                    self.__class__.__name__, attr))

    #
    # =================== INTERNAL METHODS ====================================
    #
    def addLocalSessionSDP(self, msg):
        ls = self.localSession
        if not ls:
            return
        log.debug("Add SDP")
        try:
            sdpBody = ls.sdp()
        except SDPIncomplete as exc:
            log.warning(
                "Party has an incomplete media session, so sending INVITE "
                "with no SDP: %s", exc)
            sdpBody = None
        if sdpBody is not None:
            msg.addBody(Body(type=sdpsyntax.SIPBodyType, content=sdpBody))

    def _dlg_resolveTarget(self, target):
        if self.remote_name is None:
            if target is None:
                raise ValueError("No target set to send to.")

        if target is None:
            target = self.remote_name
            log.debug("Use cached address %r", target)
            return target

        log.debug("Use supplied target %r", target)
        self.remote_name = target
        return target
