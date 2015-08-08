"""party.py

Implements the `Party` object.

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
import socket
import logging
import copy
import weakref
import re
import time
import socket

from sipparty import (util, vb, parse, fsm)
from sipparty.sip import Transport, SIPTransport
import transport
import siptransport
import prot
import components
import scenario
import defaults
import request
from message import (Message, Response)
import message
import param
from dialogs import SimpleCall

__all__ = ('Party', 'PartySubclass')

log = logging.getLogger(__name__)
bytes = six.binary_type


class PartyException(Exception):
    "Generic party exception."


class NoConnection(PartyException):
    """Exception raised when the connection cannot be created to a remote
    contact, or it is lost."""


class UnexpectedState(PartyException):
    "The party entered an unexpected state."


class Timeout(PartyException):
    "Timeout waiting for something to happen."


def NewAOR():
    newaor = defaults.AORs.pop(0)
    defaults.AORs.append(newaor)
    return newaor


class PartyMetaclass(type):
    def __init__(cls, name, bases, dict):
            super(PartyMetaclass, cls).__init__(name, bases, dict)

            # Add any predefined transitions.
            if hasattr(cls, "ScenarioDefinitions"):
                cls.SetScenario(cls.ScenarioDefinitions)


@six.add_metaclass(PartyMetaclass)
class Party(vb.ValueBinder):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    #
    # =================== CLASS INTERFACE ====================================
    #
    MessageBindings = [
        ("..aor", "FromHeader.field.value.uri.aor"),
        (".._pt_contactAddress", "ContactHeader.field.value.uri.aor.host.host",
         lambda addrTuple: addrTuple[0] if addrTuple is not None else None),
        (".._pt_contactAddress", "ContactHeader.field.value.uri.aor.host.port",
         lambda addrTuple: addrTuple[1] if addrTuple is not None else None),
    ]
    _vb_bindings = [
        ("_pt_transport.socketType",
         "_pt_outboundRequest.ViaHeader.field.transport",
         lambda x: transport.SockTypeName(x)),
        ("calleeAOR", "_pt_outboundRequest.startline.uri.aor"),
    ]
    vb_dependencies = [
        ("scenario", ["state", "wait", "waitForStateCondition"]),
        ("_pt_transport", [
            "localAddress", "localAddressPort", "listen", "connect"])]

    Scenario = None

    InviteDialog = None

    @classmethod
    def SetScenario(cls, scenario_definition):
        if cls.Scenario is not None:
            raise AttributeError(
                "Scenario for class %r is already set." % (cls.__name__,))
        SClass = scenario.Scenario.ClassWithDefinition(
            cls.__name__, scenario_definition)

        log.debug(
            "Inputs for scenario %r: %r.", SClass.__name__, SClass.Inputs)

        for input in SClass.Inputs:
            if isinstance(input, bytes) and hasattr(cls(), input):
                raise KeyError(
                    "Invalid input %r in scenario: class %r uses that as an "
                    "attribute!" % (
                        input, cls.__name__))
        cls.Scenario = SClass

    #
    # =================== INSTANCE INTERFACE =================================
    #
    aor = util.DerivedProperty("_pt_aor", set="setAOR")

    contactAddress = util.DerivedProperty("_pt_contactAddress")
    contactAddressHost = util.DerivedProperty(
        "_pt_contactAddress", get=lambda obj, underlying: underlying[0],
        set=lambda obj, val: obj._pt_contactAddress.__setitem__(0, val))
    contactAddressPort = util.DerivedProperty(
        "_pt_contactAddress", get=lambda obj, underlying: underlying[1],
        set=lambda obj, val: obj._pt_contactAddress.__setitem__(1, val))
    transport = util.DerivedProperty("_pt_transport")

    def __init__(
            self, aor=None, username=None, host=None, displayname=None,
            socketType=socket.SOCK_STREAM):
        """Create the party.
        """
        super(Party, self).__init__()

        self._pt_provInviteDialogs = {}
        self._pt_establishedInviteDialogs = {}

        # Mapping of messages based on type.
        self._pt_requestMessages = {}
        self._pt_aor = None
        self._pt_contactAddress = None
        self._pt_transport = None

        if aor is not None:
            self.aor = components.AOR.ExtractAOR(aor)

        if False:
            lAddr = self.aor.host.host
            lPort = self.aor.host.port
            self._pt_contactAddress = (lAddr, lPort)
            log.debug(
                "AOR: %r gave contact address %r", aor,
                self._pt_contactAddress)

        tp = SIPTransport()
        self.transport = tp
        tp.DefaultTransportType = socketType
        log.debug("transport sock type: %s", transport.SockTypeName(
            tp.DefaultTransportType))

        return

    def listen(self):

        assert self.aor is not None, (
            "Need an AOR before we can listen for ")

        if self._pt_contactAddress is not None:
            cAddr = self._pt_contactAddress[0]
            cPort = self._pt_contactAddress[1]
        else:
            cAddr = None
            cPort = None

        log.debug("Listen on host:%r, port:%r", cAddr, cPort)
        self._pt_contactAddress = self._pt_transport.listen(
            lHostName=cAddr, port=cPort)
        log.info(
            "Party listening on %r", self._pt_contactAddress)

        self._pt_transport.addDialogHandlerForAOR(
            self.aor, self.newDialogHandler)

    def invite(self, target, proxy=None):

        if not hasattr(self, "aor"):
            raise AttributeError(
                "Cannot build a request since we aren't configured with an "
                "AOR!")

        aor = components.AOR.ExtractAOR(target)

        if proxy is None:
            proxy = self._pt_resolveProxyHostFromTarget(target)

        invD = self.addNewInviteDialog()
        invD.target = target

        log.debug("Initialize dialog to %r", proxy)
        invD.initiate(proxy)
        return invD

    def addNewInviteDialog(self):
        InviteDialog = self.InviteDialog
        if InviteDialog is None:
            raise AttributeError(
                "Cannot build an INVITE dialog since we aren't configured "
                "with a Dialog Type to use!")

        invD = InviteDialog()
        self._pt_configureDialog(invD)

        pdid = invD.provisionalDialogID
        pdis = self._pt_provInviteDialogs
        assert pdid not in pdis
        pdis[pdid] = invD

        return invD

    def waitUntilState(self, state, error_state=None, timeout=None):
        for check_state in (state, error_state):
            if check_state is not None and check_state not in self.States:
                raise AttributeError(
                    "%r instance has no state %r." % (
                        self.__class__.__name__, check_state))

        self.scenario.waitForStateCondition(
            lambda x: x in (state, error_state), timeout=timeout)

        if self.state == error_state:
            raise UnexpectedState(
                "%r instance has entered the error state %r while "
                "waiting for state %r." % (
                    self.__class__.__name__, error_state, state))

    def setAOR(self, value):
        if self.aor is not None:
            raise AttributeError(
                "Cannot set AOR %s since %r instance already has AOR %s." % (
                    value, self.__class__.__name__, self.aor))
        self._pt_aor = value

    #
    # =================== DELEGATE IMPLEMENTATIONS ===========================
    #
    def scenarioDelegateReset(self):
        log.debug("Resetting after scenario reset.")
        self.myTag = None
        self.theirTag = None

    def newDialogHandler(self, message):
        if message.type == Message.types.invite:
            invD = self.addNewInviteDialog()
            invD.receiveMessage(message)
            return

    #
    # =================== MAGIC METHODS ======================================
    #
    def __getattr__(self, attr):

        if attr.startswith(b"message"):
            messageType = attr.replace(b"message", b"", 1)
            if messageType in self._pt_requestMessages:
                return self._pt_requestMessages[messageType]

        try:
            return super(Party, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} instance has no attribute "
                "{attr!r}.."
                "".format(**locals()))

        if attr == "States":
            try:
                return getattr(self.Scenario, attr)
            except AttributeError:
                raise AttributeError(
                    "%r instance has no attribute %r as it is not "
                    "configured with a Scenario." % (
                        self.__class__.__name__, attr))

        internalSendPrefix = "_send"
        if attr.startswith(internalSendPrefix):
            message = attr.replace(internalSendPrefix, "", 1)
            try:
                send_action = util.WeakMethod(
                    self, "_pt_send", static_args=[message])
            except:
                log.exception("")
                raise
            return send_action

        internalReplyPrefix = "_reply"
        if attr.startswith(internalReplyPrefix):
            message = attr.replace(internalReplyPrefix, "", 1)
            try:
                send_action = util.WeakMethod(
                    self, "_pt_reply", static_args=[message])
            except:
                log.exception("")
                raise
            return send_action

        scn = self.scenario
        if scn is not None and attr in scn.Inputs:
            try:
                scn_action = util.WeakMethod(
                    scn, "hit", static_args=[attr])
                return scn_action
            except:
                log.exception("")
                raise

        try:
            return super(Party, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} instance has no attribute "
                "{attr!r}; scenario inputs were {scn.Inputs}."
                "".format(**locals()))

    #
    # =================== INTERNAL METHODS ===================================
    #
    def _pt_configureDialog(self, dialog):
        for attr in ("aor", "transport", "contactAddress"):
            setattr(dialog, attr, getattr(self, attr))

    def _pt_resolveProxyHostFromTarget(self, target):
        try:
            if hasattr(target, "contactAddress"):
                return target.contactAddress

            aor = self._pt_resolveAORFromObject(target)
            return aor.host
        except TypeError:
            raise TypeError(
                "%r instance cannot be derived from %r instance." % (
                    components.Host.__class__.__name__,
                    target.__class__.__name__))

    def _pt_resetScenario(self):
        self.scenario = None
        if self.Scenario is not None:
            self.scenario = self.Scenario(delegate=self)
            self.scenario.actionCallback = util.WeakMethod(
                self, "scenarioActionCallback")

    def _pt_transformForReply(self, inputMessageType, responseType):
        #! Remove this!
        assert 0
        indct = transform.EntryForMessageType(self.transform, inputMessageType)
        tform = transform.EntryForMessageType(indct, responseType)
        return tform


def PartySubclass(name, transitions):
    return type(name + "Party", (Party,), {"ScenarioDefinitions": transitions})
