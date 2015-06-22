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

from sipparty import (util, vb, parse)
import transport
import siptransport
import prot
import components
import scenario
import defaults
import request
from message import (Message, Response)
import transform
import message
import param

__all__ = ('Party',)

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
    vb_bindings = [
        ("aor",
         "_pt_outboundRequest.FromHeader.field.value.uri.aor"),
        ("_pt_transport.localAddressHost",
         "_pt_outboundRequest.ContactHeader.field.value.uri.aor.host"),
        ("_pt_transport.localAddressPort",
         "_pt_outboundRequest.ContactHeader.field.value.uri.aor.port"),
        ("_pt_transport.socketType",
         "_pt_outboundRequest.ViaHeader.field.transport",
         lambda x: transport.SockTypeName(x)),
        ("calleeAOR", "_pt_outboundRequest.startline.uri.aor"),
        ("myTag", "_pt_outboundRequest.FromHeader.field.parameters.tag"),
        ("theirTag", "_pt_outboundRequest.ToHeader.field.parameters.tag"),
        ("myTag", "_pt_outboundResponse.ToHeader.field.parameters.tag"),
        ("theirTag", "_pt_outboundResponse.FromHeader.field.parameters.tag"),
    ]
    vb_dependencies = [
        ("scenario", ["state", "wait", "waitForStateCondition"]),
        ("_pt_transport", [
            "localAddress", "localAddressPort", "listen", "connect"])]

    Scenario = None

    @classmethod
    def SetScenario(cls, scenario_definition):
        if cls.Scenario is not None:
            raise AttributeError(
                "Scenario for class %r is already set." % (cls.__name__,))
        SClass = scenario.ScenarioClassWithDefinition(
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
    aor = util.DerivedProperty("_pt_aor")

    def __init__(
            self, username=None, host=None, displayname=None,
            socketType=socket.SOCK_STREAM):
        """Create the party.
        """
        super(Party, self).__init__()

        self._pt_waitingMessage = None
        self._pt_outboundRequest = None
        self._pt_outboundResponse = None
        self.calleeAOR = None
        self.myTag = None
        self.theirTag = None

        self.aor = NewAOR()
        if username is not None:
            self.aor.username = username
        if host is not None:
            self.aor.host = host

        # Set up the transport.
        self._pt_transport = siptransport.SipTransportFSM(
            socketType=socketType)

        # Currently don't do listen until required to.
        # self._pt_transport.listen()
        self._pt_transport.messageConsumer = util.WeakMethod(
            self, "_pt_messageConsumer")

        # Set up the scenario.
        self._pt_resetScenario()

        # Set up the transform.
        if not hasattr(self, "transform"):
            self.transform = transform.default

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

    def reset(self):
        self._pt_reset()

    #
    # =================== DELEGATE IMPLEMENTATIONS ===========================
    #
    def scenarioDelegateReset(self):
        log.debug("Resetting after scenario reset.")
        self.myTag = None
        self.theirTag = None

    #
    # =================== MAGIC METHODS ======================================
    #
    def __getattr__(self, attr):

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
    def _pt_messageConsumer(self, message):
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
        self.scenario.hit(message.type, message)

    def _pt_send(self, message_type, callee=None, contactAddress=None):
        log.debug("Send message of type %r to %r.", message_type, callee)

        tp = self._pt_transport

        if self.myTag is None:
            self.myTag = param.TagParam()

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
            del msg

    def _pt_reply(self, message_type, request):
        log.debug("Reply to %r with %r.", request.type, message_type)

        if self.myTag is None:
            self.myTag = param.TagParam()

        if re.match("\d+$", message_type):
            message_type = int(message_type)
            msg = message.Response(code=message_type)
        else:
            msg = getattr(message.Message, message_type)

        tform = self.transform[request.type][message_type]
        request.applyTransform(msg, tform)

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

    def _pt_resetScenario(self):
        self.scenario = None
        if self.Scenario is not None:
            self.scenario = self.Scenario(delegate=self)
            self.scenario.actionCallback = util.WeakMethod(
                self, "scenarioActionCallback")
