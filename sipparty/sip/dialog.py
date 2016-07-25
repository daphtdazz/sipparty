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
from .. import vb
from ..fsm import (AsyncFSM, InitialStateKey, UnexpectedInput)
from ..deepclass import DeepClass, dck
from ..parse import ParsedPropertyOfClass
from ..sdp import (sdpsyntax, SDPIncomplete)
from ..util import (abytes, astr, Enum, WeakProperty)
from .transform import (Transform, TransformKeys)
from .components import URI
from .header import Call_IdHeader
from .request import Request
from .message import Message, MessageResponse
from .param import TagParam
from .body import Body
from .transaction import TransactionUser
from . import prot

log = logging.getLogger(__name__)

States = Enum((
    InitialStateKey, "SentInvite", "InDialog", "TerminatingDialog",
    "SuccessCompletion", "ErrorCompletion"))
Inputs = Enum(("initiate", "receiveRequest", "terminate"))

tfk = TransformKeys

AckTransforms = {
    200: {
        b"ACK": (
            (tfk.CopyFrom, "request", "FromHeader"),
            (tfk.Copy, "ToHeader"),
            (tfk.Copy, "CseqHeader"),
            (tfk.CopyFrom, "request", "Call_IDHeader"),
            (tfk.CopyFrom, "request", "startline.uri"),
            (tfk.CopyFrom, "request", "viaheader"),
            (tfk.CopyFrom, 'request', 'ContactHeader'),
            (tfk.Copy, "startline.protocol",),
        )
    }
}


class Dialog(
        DeepClass("_dlg_", {
            "from_uri": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "to_uri": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "contact_uri": {
                dck.descriptor: ParsedPropertyOfClass(URI), dck.gen: URI},
            "localTag": {dck.gen: TagParam},
            "remoteTag": {},
            "transport": {dck.descriptor: WeakProperty},
            "localSession": {},
            "remoteSession": {},
            'callIDHeader': {}}),
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
            self.callIDHeader.value, self.localTag.value)

    @property
    def dialogID(self):
        rt = self.remoteTag
        if rt is None:
            raise AttributeError(
                "%r instance has no remote tag so is not yet in a dialog so "
                "does not have a dialogID." % (self.__class__.__name__,))
        return prot.EstablishedDialogID(
            self._dlg_callIDHeader.value, self.localTag.value, rt.value)

    def __init__(self, transport, **kwargs):
        log.info('New %s instance', type(self).__name__)
        kwargs['transport'] = transport
        super(Dialog, self).__init__(**kwargs)
        self._dlg_requests = []

    def initiate(self, *args, **kwargs):
        log.debug("Initiating dialog...")
        self.hit(Inputs.initiate, *args, **kwargs)

    def terminate(self, *args, **kwargs):
        self.hit(Inputs.terminate, *args, **kwargs)

    def consume_message(self, msg):

        log.debug("Dialog receiving message")
        log.detail("%r", msg)
        mtype = msg.type

        def RaiseBadInput(msg=b""):
            raise(UnexpectedInput(
                "%r instance fsm has no input for message type %r." % (
                    self.__class__.__name__, mtype)))

        if self.callIDHeader is None:
            self.callIDHeader = msg.Call_IDHeader

        if self.remoteTag is None:
            if msg.isresponse():
                log.debug("Message is a response")
                rtag = msg.ToHeader.parameters.tag
            else:
                log.debug("Message is a request")
                rtag = msg.FromHeader.parameters.tag
            log.debug("Learning remote tag: %s", rtag.value)
            self.remoteTag = rtag
            tp = self.transport
            if tp is not None:
                tp.updateDialogGrouping(self)

        if self.contact_uri is None:
            cURI = msg.ContactHeader.uri
            log.debug("Learning contact_uri: %r", cURI)
            self.contact_uri = cURI

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

    def send_ack(self, msg):
        ack = Message.ACK(autofillheaders=False)
        assert len(self._dlg_requests)

        mtype = msg.type
        if isinstance(mtype, str):
            mtype = abytes(mtype)
        Transform(
            AckTransforms, msg, mtype, ack, abytes(ack.type),
            request=self._dlg_requests[-1])

        self.__send_message(ack)

    def send_request(self, req_type, remote_name=None, remote_port=None):

        if remote_name is not None:
            log.debug("Learning remote address: %r", remote_name)
            self.remote_name = astr(remote_name)

        if remote_port is not None:
            log.debug("Learning remote port: %r", remote_port)
            self.remote_port = remote_port

        for reqdAttr in (
                "from_uri", "to_uri", "contact_uri", "remote_name",
                "transport"):
            attrVal = getattr(self, reqdAttr)
            if attrVal is None:
                raise ValueError(
                    "Attribute %r of %r instance required to send a request "
                    "is None." % (
                        reqdAttr, self.__class__.__name__))

        req = getattr(Message, req_type)()
        req.startline.uri = deepcopy(self.to_uri)
        req.ToHeader.uri = deepcopy(self.to_uri)

        req.FromHeader.field.value.uri = deepcopy(self.from_uri)
        req.ContactHeader.uri = deepcopy(self.contact_uri)

        req.FromHeader.parameters.tag = deepcopy(self.localTag)
        req.ToHeader.parameters.tag = deepcopy(self.remoteTag)

        if self.callIDHeader is None:
            self.callIDHeader = Call_IdHeader()
        req.Call_IdHeader = deepcopy(self.callIDHeader)

        log.debug("send request of type %r", req.type)

        if req.type == req.types.invite:
            self.addLocalSessionSDP(req)

        self.__send_message(req)
        req.unbindAll()
        self._dlg_requests.append(req)
        self.transport.updateDialogGrouping(self)

    def send_response(self, response, req):
        log.debug("Send response type %r.", response)

        resp = MessageResponse(response)
        self.configureResponse(resp, req)
        vh = req.viaheader
        self.transport.send_message(resp, astr(vh.address), vh.port)

    def configureResponse(self, resp, req):
        log.debug('Transform %s to %s', req.type, resp.type)
        Transform(self.Transforms, req, req.type, resp, resp.type)

        if req.type == req.types.invite and resp.type == 200:
            self.addLocalSessionSDP(resp)

        resp.FromHeader.parameters.tag = self.remoteTag
        resp.ToHeader.parameters.tag = self.localTag

    def hasTerminated(self):
        """Dialog is over. Remove it from the transport."""
        tp = self.transport
        if tp is not None:
            tp.removeDialog(self)

    def session_listen(self, *args, **kwargs):
        if self.localSession is not None:
            self.localSession.listen()

    #
    # =================== DELEGATE METHODS ====================================
    #

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        log.info('DELETE %s instance', type(self).__name__)
        getattr(super(Dialog, self), '__del__', lambda: None)()

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

    def __send_message(self, msg):
        # At this point we have transformed if necessary.
        # Get a transaction for this message.
        tm = self.transaction_manager
        if tm is not None:
            try:
                trns = self.transaction_manager.lookup_transaction(msg)
            except KeyError as exc:
                log.debug(
                    'No existing transaction for message, error: %s', exc)
            else:
                return self.__send_msg_through_trns(msg, trns)

        if tm is not None and msg.isrequest():
            trns = tm.new_transaction_for_request(
                msg, self.transport, self, remote_name=self.remote_name,
                remote_port=self.remote_port)
            if trns is not None:
                log.debug('Got new transaction for request')
                return self.__send_msg_through_trns(msg, trns)

        tp = self.transport
        if tp is None:
            raise AttributeError(
                '%r instance has no transport attribute or transactions so '
                'cannot send a message.' % (type(self).__name__,))

        try:
            ad = tp.send_message(msg, self.remote_name, self.remote_port)
            self.remote_name = ad.remote_name
            self.remote_port = ad.remote_port
        except prot.Incomplete:
            log.error("Incomplete message of type %s", msg.type)
            raise

    def __send_msg_through_trns(self, msg, trns):
        trns.hit('request', msg)
        self.remote_name = trns.remote_name
        self.remote_port = trns.remote_port

TransactionUser.register(Dialog)
