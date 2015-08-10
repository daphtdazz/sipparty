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
import numbers

from sipparty import (splogging, vb, util, fsm, ParsedPropertyOfClass)
from sipparty.fsm import (FSM, UnexpectedInput)
from sipparty.deepclass import DeepClass, dck
from components import (AOR, URI)
from header import Call_IdHeader
from request import Request
from response import Response
from message import Message, Response
from param import TagParam
import prot

log = logging.getLogger(__name__)
bytes = six.binary_type

States = util.Enum((
    fsm.InitialStateKey, "InitiatingDialog", "InDialog", "TerminatingDialog",
    "SuccessCompletion", "ErrorCompletion"))
Inputs = util.Enum((
    "initiate", "receiveRequest", "terminate"))
TransformKeys = util.Enum((
    "Copy", "Add", "CopyFromRequest"))
Tfk = TransformKeys


class Dialog(
        DeepClass("_dlg_", {
            "fromURI": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "toURI": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "contactURI": {dck.descriptor: ParsedPropertyOfClass(URI)},
            "remoteAddress": {},
            "localTag": {},
            "remoteTag": {},
            "transport": {}}),
        fsm.FSM, vb.ValueBinder):
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
    vb_bindings = [
    ]
    vb_dependencies = [
        ("transport", ["sendMessage"])
    ]
    Transforms = None

    #
    # =================== INSTANCE INTERFACE ==================================
    #

    @property
    def provisionalDialogID(self):
        return prot.ProvisionalDialogID(
            self._dlg_callIDHeader.field, self.localTag.value)

    @property
    def dialogID(self):
        rt = self.remoteTag
        if rt is None:
            raise AttributeError(
                "%r instance has no remote tag so is not yet in a dialog so "
                "does not have a dialogID." % (self.__class__.__name__,))
        return prot.EstablishedDialogID(
            self._dlg_callIDHeader.field, self.localTag.value, rt.value)

    def __init__(self, **kwargs):
        super(Dialog, self).__init__(**kwargs)

        self._dlg_callIDHeader = None
        self._dlg_localTag = TagParam()
        self._dlg_remoteTag = None

    def initiate(self, *args, **kwargs):
        log.debug("Initiating dialog...")
        self.hit(Inputs.initiate, *args, **kwargs)

    def terminate(self, *args, **kwargs):
        self.hit(Inputs.terminate, *args, **kwargs)

    def receiveMessage(self, msg):

        log.debug("Dialog receiving message")
        log.detail("%r", msg)

        mtype = msg.type

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
                self.transport.updateDialogGrouping(self)

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
            attr = b"receiveResponse%d" % mtype
            if attr in self.Inputs:
                log.debug("Response input found: %d", mtype)
                return self.hit(attr, msg)
            mtype /= 10

        RaiseBadInput()

    def sendRequest(self, type, remoteAddress=None):

        if self._dlg_callIDHeader is None:
            log.debug("First request, generate call ID header.")
            self._dlg_callIDHeader = Call_IdHeader()

        if remoteAddress is not None:
            log.debug("Learning remote address: %r", remoteAddress)
            self.remoteAddress = remoteAddress

        for reqdAttr in (
                "fromURI", "toURI", "contactURI", "remoteAddress",
                "transport"):
            attrVal = getattr(self, reqdAttr)
            if attrVal is None:
                raise ValueError(
                    "Attribute %r of %r instance required to send a request "
                    "is None." % (
                        reqdAttr, self.__class__.__name__))

        req = getattr(Message, type)()
        req.startline.uri = self.toURI
        req.ToHeader.uri = self.toURI

        req.FromHeader.field.value.uri = self.fromURI
        req.ContactHeader.uri = self.contactURI
        req.ViaHeader.field.host = self.contactURI.aor.host

        req.FromHeader.parameters.tag = self.localTag
        req.ToHeader.parameters.tag = self.remoteTag
        req.Call_IdHeader = self._dlg_callIDHeader

        log.debug("send request of type %r", req.type)

        tp = self.transport
        if tp is None:
            raise AttributeError(
                "%r instance has no transport attribute so cannot send a "
                "request." % (self.__class__.__name__,))

        try:
            reqb = bytes(req)
        except prot.Incomplete:
            log.error("Incomplete message: %r", req)
            raise

        tp.sendMessage(bytes(req), self.remoteAddress)
        tp.updateDialogGrouping(self)

    def sendResponse(self, response, req):
        log.debug("Send response type %r.", response)

        resp = Response(response)

        reqtforms = self.Transforms[req.type]

        code = response
        while code > 0:
            if code in reqtforms:
                break
            code /= 10
        else:
            raise KeyError(
                "%r instance has no transform for %r -> %r." % (
                    self.__class__.__name__, req.type, code))

        tform = reqtforms[code]

        self.configureResponse(resp, req, tform)
        self.transport.sendMessage(
            bytes(resp), req.ContactHeader.host)

    def configureResponse(self, resp, req, tform):
        log.debug("Configure response starting %r, startline %r", resp,
                  resp.startline)

        def raiseActTupleError(tp, msg):
            raise ValueError(
                "%r instance transform action %r is unrecognisable: %s" % (
                    self.__class__.__name__, tp, msg))

        for actTp in tform:
            action = actTp[0]

            if action not in Tfk:
                raiseActTupleError(actTp, "Unrecognised action %r." % action)
            if action == Tfk.Copy:
                if len(actTp) < 2:
                    raiseActTupleError(actTp, "No path to copy.")
                path = actTp[1]
                val = req.attributeAtPath(path)
                resp.setAttributePath(path, val)
                continue

            if action == Tfk.Add:
                if len(actTp) < 3:
                    raiseActTupleError(actTp, "No generator for Add action.")
                path = actTp[1]
                gen = actTp[2]
                resp.setAttributePath(path, gen(req))
                continue

            if action == Tfk.CopyFromRequest:
                assert 0

            assert 0

        resp.FromHeader.parameters.tag = self.remoteTag
        resp.ToHeader.parameters.tag = self.localTag
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
        "^sendRequest(%s)$" % "|".join(Request.types), re.IGNORECASE)
    sendResponseRE = re.compile("^sendResponse([0-9]+)$", re.IGNORECASE)

    def __getattr__(self, attr):

        mo = Dialog.sendRequestRE.match(attr)
        if mo:
            method = getattr(Request.types, mo.group(1))
            log.debug("Method is type %r", method)
            return util.WeakMethod(
                self, "sendRequest", static_args=(method,))

        mo = Dialog.sendResponseRE.match(attr)
        if mo:
            code = int(mo.group(1))
            while code < 100:
                code *= 100
            return util.WeakMethod(
                self, "sendResponse", static_args=(code,))

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
    def _dlg_resolveTarget(self, target):
        if self._dlg_remoteAddress is None:
            if target is None:
                raise ValueError("No target set to send to.")

        if target is None:
            target = self._dlg_remoteAddress
            log.debug("Use cached address %r", target)
            return target

        log.debug("Use supplied target %r", target)
        self._dlg_remoteAddress = target
        return target
