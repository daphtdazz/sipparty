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
from numbers import Integral

from .. import vb
from ..classmaker import classbuilder
from ..fsm import (AsyncFSM, InitialStateKey, UnexpectedInput)
from ..deepclass import DeepClass, dck
from ..parse import ParsedPropertyOfClass
from ..sdp import (sdpsyntax, SDPIncomplete)
from ..util import (abytes, astr, Enum, WeakProperty)
from . import prot
from .body import Body
from .components import URI
from .header import Call_IdHeader
from .message import Message, MessageResponse
from .param import TagParam
from .request import Request
from .standardtimers import StandardTimers
from .transaction import TransactionUser
from .transform import (Transform, TransformKeys)

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


@classbuilder(bases=(
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
    TransactionUser, StandardTimers, AsyncFSM, vb.ValueBinder))
class Dialog:
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
        self.__request = None
        self.__last_response = None

    def initiate(self, *args, **kwargs):
        log.debug("Initiating dialog...")
        self.hit(Inputs.initiate, *args, **kwargs)

    def terminate(self, *args, **kwargs):
        self.hit(Inputs.terminate, *args, **kwargs)

    def resend_response(self):
        assert self.__last_response is not None
        tp = self.transport
        if tp is None:
            log.warning(
                'Failed to resend %s response as transport has been '
                'released.' % (
                    self.__last_response.type,))
            return

        tp.send_message_with_transaction(
            self.__last_response, self, remote_name=self.remote_name,
            remote_port=self.remote_port)

    def send_ack(self, msg):
        ack = Message.ACK(autofillheaders=False)
        assert len(self._dlg_requests)

        mtype = msg.type
        if isinstance(mtype, str):
            mtype = abytes(mtype)
        Transform(
            AckTransforms, msg, mtype, ack, abytes(ack.type),
            request=self._dlg_requests[-1])

        tp = self.transport
        if tp is None:
            log.warning('Failed to send ACK as transport has been released.')
            return

        tp.send_message_with_transaction(
            ack, self, remote_name=self.remote_name,
            remote_port=self.remote_port)

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
                    "Attribute %r of %r instance required to send %s request "
                    "is None." % (req_type, reqdAttr, self.__class__.__name__))
            if reqdAttr == 'transport':
                # Transport is weak so ensure we retain it here.
                tp = attrVal

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

        tp.send_message_with_transaction(
            req, self, self.remote_name, self.remote_port)
        req.unbindAll()
        self._dlg_requests.append(req)
        tp.updateDialogGrouping(self)

    def send_response(self, response_code, req=None):
        log.debug("Send response type %r.", response_code)

        if req is None:
            req = self.__request
        assert req is not None

        resp = MessageResponse(response_code)
        self.configureResponse(resp, req)
        vh = req.viaheader
        tp = self.transport
        if tp is None:
            log.warning(
                'Unable to send %s response to %s request as transport has '
                'been released' % (response_code, req.type))
            return

        self.transport.send_message_with_transaction(
            resp, self, astr(vh.address), vh.port)
        self.__last_response = resp

    def configureResponse(self, resp, req):
        log.debug('Transform %s to %s', req.type, resp.type)
        Transform(self.Transforms, req, req.type, resp, resp.type)

        if req.type == req.types.invite and resp.type == 200:
            self.addLocalSessionSDP(resp)

        resp.FromHeader.parameters.tag = self.remoteTag
        resp.ToHeader.parameters.tag = self.localTag

    def session_listen(self, *args, **kwargs):
        if self.localSession is not None:
            self.localSession.listen()

    #
    # =================== TRANSACTION USER METHODS ============================
    #
    def request(self, msg):
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
            rtag = msg.FromHeader.parameters.tag
            log.debug("Learning remote tag: %s", rtag)
            self.remoteTag = rtag
            self.transport.updateDialogGrouping(self)

        return self.hit(
            'receiveRequest' + getattr(Request.types, mtype), msg)

    def response(self, msg):

        log.debug("Dialog receiving response")
        log.detail("%r", msg)
        mtype = msg.type

        if self.remoteTag is None:
            rtag = msg.ToHeader.parameters.tag
            log.debug("Learning remote tag: %s", rtag.value)
            self.remoteTag = rtag
            self.transport.updateDialogGrouping(self)

        if not isinstance(mtype, Integral):
            self.raise_unexpected_input('response %r' % (mtype,))

        rinp = self._fix_response_input(mtype)

        self.hit(rinp, msg)

    def timeout(self, error):
        rinp = self._fix_response_input(408)
        self.hit(rinp, error)

    def transport_error(self, error):
        rinp = self._fix_response_input(503)
        self.hit(rinp, error)

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

    def _fix_response_input(self, mtype):
        orig_mtype = mtype
        while mtype >= 1:
            attr = "response_%d" % mtype
            if attr in self.Inputs:
                log.debug("Response input found: %d", mtype)
                return attr

            mtype /= 10

        # Didn't find one, perhaps there is an xxx response.
        if 'response_xxx' in self.Inputs:
            return 'response_xxx'
        self.raise_unexpected_input('response_%d' % (orig_mtype,))
