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
from message import (Message, Response)
import transform
import pdb

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
            cls.scenario = (
                None if not hasattr(cls, "ScenarioDefinitions") else
                scenario.ScenarioClassWithDefinition(
                    name, cls.ScenarioDefinitions))

            log.debug("PartyMetaclass init done.")


@six.add_metaclass(PartyMetaclass)
class Party(object):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    aor = _util.DerivedProperty("_pt_aor")

    def __init__(self, username=None, host=None, displayname=None):
        """Create the party.
        """

        self.aor = NewAOR()
        if username is not None:
            self.aor.username = username
        if host is not None:
            self.aor.host = host

        # Set up the transport.
        self._pt_transport = siptransport.SipTransportFSM()
        # self._pt_transport.byteConsumer = self._pt_byteConsumer

        # !!! Make a new SIPTransportFSM class to handle sip transport
        # !!! requirements?

if 0:
    def _sendinvite(self, callee):
        """Start a call."""
        invite = Message.invite()
        invite.startline.uri.aor = copy.deepcopy(callee.aor)
        invite.fromheader.field.value.uri.aor = copy.deepcopy(self.aor)
        invite.viaheader.field.transport = transport.SockTypeName(
            callee.socktype)
        self.connect(
            callee.address, callee.port, callee.sockfamily, callee.socktype)
        self.active_socket.sendall(str(invite))

    def receiveMessage(self):
        if hasattr(self, "active_socket"):
            sock = self.active_socket
        else:
            sock = self.passive_socket

        if sock.type == socket.SOCK_STREAM:
            assert 0, "Stream sockets not yet supported."
        else:
            data, addr = sock.recvfrom(4096)

        msg = Message.Parse(data)
        log.debug("Received message %s", msg)
        return msg

    def _respond(self, code):
        """Send a SIP response code."""
        msg = self.receiveMessage()

        if msg.isresponse():
            raise prot.ProtocolError("Cannot respond to a response.")

        try:
            tform = transform.request[msg.type][code]
        except KeyError:
            log.error("No transformation for %d from %s", code, msg.type)

        rsp = Response(code)
        log.debug("Initial response:%r", str(rsp))
        msg.applyTransform(rsp, tform)
        log.debug("Proto-response: %s", rsp)

    # Receiving methods.
    def receive_response(self, code):
        """Receive a response code after a request."""

    #
    # =================== INTERNAL ===========================================
    #
    def _pt_byteConsumer(self, data):
        return len(data)
