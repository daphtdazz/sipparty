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
from request import Request
from message import Message
from param import TagParam

log = logging.getLogger(__name__)
bytes = six.binary_type

States = util.Enum((
    fsm.InitialStateKey, "InitiatingDialog", "InDialog", "TerminatingDialog",
    "SuccessCompletion", "ErrorCompletion"))
Inputs = util.Enum((
    "initiate", "receiveRequest", "terminate"))


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

    def receiveMessage(self, msg):
        if msg.type in Request.types:
            input = "receiveRequest" + msg.type.lower().capitalize()
            return self.hit(input, msg)

        return getattr(self, b"receiveResponse" + bytes(msg.type))(msg)

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

        self.transport.sendMessage(bytes(req), toAddr)

    def sendResponse(self, response, req):
        req.FromHeader.parameters.tag = self.remoteTag
        req.ToHeader.parameters.tag = self.localTag
        assert 0

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

        log.debug("Try and get dialog attribute %r", attr)
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
            log.debgu("Matches nothing so far.")
            return super(Dialog, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "%r instance has no attribute %r." % (
                    self.__class__.__name__, attr))
