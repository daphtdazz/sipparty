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
import _util
import transport
import siptransport
import prot
import components
import scenario
import defaults
import request
from message import (Message, Response)
import transform
import weakref
import re
import message
import vb

__all__ = ('Party',)

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def NewAOR():
    newaor = defaults.AORs.pop(0)
    defaults.AORs.append(newaor)
    return newaor


class PartyMetaclass(type):
    def __init__(cls, name, bases, dict):
            super(PartyMetaclass, cls).__init__(name, bases, dict)
            log.debug("PartyMetaclass init")

            # Add any predefined transitions.
            cls.Scenario = (
                None if not hasattr(cls, "ScenarioDefinitions") else
                scenario.ScenarioClassWithDefinition(
                    name, cls.ScenarioDefinitions))

            log.debug("PartyMetaclass init done.")


@six.add_metaclass(PartyMetaclass)
class Party(vb.ValueBinder):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    bindings = [
        ("outBoundMessage.", "something_else")
    ]
    vb_dependencies = [
        ("scenario", ["state"])]

    aor = _util.DerivedProperty("_pt_aor")

    def __init__(self, username=None, host=None, displayname=None):
        """Create the party.
        """
        super(Party, self).__init__()

        self._pt_waitingMessage = None

        self.aor = NewAOR()
        if username is not None:
            self.aor.username = username
        if host is not None:
            self.aor.host = host

        # Set up the transport.
        self._pt_transport = siptransport.SipTransportFSM()

        # Currently don't do listen until required to.
        # self._pt_transport.listen()
        self._pt_transport.messageConsumer = _util.WeakMethod(
            self, "_pt_messageConsumer")

        # Set up the scenario.
        if self.Scenario is not None:
            self.scenario = self.Scenario(delegate=self)
            self.scenario.actionCallback = _util.WeakMethod(
                self, "scenarioActionCallback")

        # Set up the transform.
        if not hasattr(self, "transform"):
            self.transform = transform.default

        # !!! Make a new SIPTransportFSM class to handle sip transport
        # !!! requirements?

    def __getattr__(self, attr):

        if attr.startswith("send"):
            message = attr.replace("send", "", 1)
            try:
                send_action = _util.WeakMethod(
                    self, "_pt_send", static_args=[message])
            except:
                log.exception("")
                raise
            return send_action

        if attr.startswith("reply"):
            message = attr.replace("reply", "", 1)
            try:
                send_action = _util.WeakMethod(
                    self, "_pt_reply", static_args=[message])
            except:
                log.exception("")
                raise
            return send_action

        if attr in request.Request.types:
            na = getattr(request.Request.types, attr)

            def scenario_input(*args, **kwargs):
                self.scenario.hit(na, *args, **kwargs)
            return scenario_input

        try:
            return super(Party, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} instance has no attribute "
                "{attr!r}."
                "".format(**locals()))

    def scenarioActionCallback(self, message_type, *args, **kwargs):
        log.debug("Message to send: %r.", message_type)

        if re.match("\d+", message_type):
            msg = message.Response(int(message_type))
        else:
            msg = getattr(message.Message, message_type)

        if "message" in kwargs:
            log.debug("  responding to a received message.")
            rcvdMessage = kwargs[message]
            rcvdMessage.applyTransform(msg, self.transform)
            self._pt_transport.sendMessage(msg)
        else:
            self._pt_transport.sendMessage(msg)

    #
    # =================== INTERNAL ===========================================
    #
    def _pt_messageConsumer(self, message):
        log.debug("Received a %r message.", message.type)
        self.scenario.hit(message.type, message)

    def _pt_send(self, message_type, callee):
        msg = getattr(Message, message_type)()
        msg.startline.uri.aor = copy.deepcopy(callee.aor)
        msg.fromheader.field.value.uri.aor = copy.deepcopy(self.aor)
        msg.viaheader.field.transport = transport.SockTypeName(
            callee._pt_transport.type)
        if self._pt_transport.state != self._pt_transport.States.connected:
            self._pt_transport.connect(callee._pt_transport.localAddress)
            _util.WaitFor(
                lambda: (self._pt_transport.state ==
                         self._pt_transport.States.connected),
                1.0)
        self._pt_transport.send(str(msg))

    def _pt_reply(self, message_type, request):
        if re.match("\d+$", message_type):
            msg = message.Response(code=int(message_type))
        else:
            msg = getattr(message.Message, message_type)

        request.applyTransform(msg, self.transform)

        self.active_socket.sendall(str(msg))
