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

from sipparty import (vb, util, fsm)
from sipparty.fsm import (FSM, UnexpectedInput)
import header
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


class Dialog(fsm.FSM, vb.ValueBinder):
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
            self._dlg_callIDHeader.field, self.localTag.value, rt)

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

    def receiveMessage(self, msg):

        mtype = msg.type
        def RaiseBadInput(msg=b""):
            raise(UnexpectedInput(
                "%r instance fsm has no input for message type %r." % (
                    self.__class__.__name__, mtype)))

        if self.remoteTag is None:
            rtag = msg.FromHeader.parameters.tag
            log.debug("Learning remote tag: %r", rtag)
            self.remoteTag = rtag
            tp = self.transport
            if tp is not None:
                self.transport.updateDialogGrouping(self)

        if mtype in Request.types:
            input = "receiveRequest" + msg.type.upper()
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

    def sendRequest(self, type, toAddr):
        # TODO: write
        #
        # Transaction or not?
        #
        # Transform:

        req = getattr(Message, type)()
        req.startline.uri.aor = self.aor
        req.FromHeader.field.value.uri.aor = self.aor
        contact_host = req.ContactHeader.field.value.uri.aor.host
        contact_host.host = self.contactAddress[0]
        contact_host.port = self.contactAddress[1]

        req.FromHeader.parameters.tag = self.localTag
        req.ToHeader.parameters.tag = self.remoteTag
        req.Call_IDHeader = self.callIDHeader

        log.debug("send request of type %r", req.type)

        tp = self.transport
        if tp is None:
            raise AttributeError(
                "%r instance has no transport attribute so cannot send a "
                "request." % (self.__class__.__name__,))
        tp.sendMessage(bytes(req), toAddr)
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
            bytes(resp), req.ContactHeader.field.value.uri.aor.host)

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
    def messageConsumer(self, message):
        assert 0
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
