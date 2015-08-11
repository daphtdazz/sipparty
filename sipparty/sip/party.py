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
from six import itervalues

from sipparty import (splogging, util, vb, parse, fsm, ParsedPropertyOfClass)
from sipparty.util import DerivedProperty
from sipparty.deepclass import DeepClass, dck
from sipparty.sip import SIPTransport
from sipparty.transport import SockTypeName
import prot
from components import (DNameURI, AOR, URI, Host)
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
class Party(
        DeepClass("_pt_", {
            "dnameURI": {
                dck.check: lambda dnu: isinstance(dnu, DNameURI),
                dck.gen: DNameURI},
            "contactURI": {
                dck.descriptor: ParsedPropertyOfClass(URI),
                dck.gen: URI},
            "transport": {dck.gen: lambda: None}}),
        vb.ValueBinder):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    #
    # =================== CLASS INTERFACE ====================================
    #
    InviteDialog = None

    vb_dependencies = [
        ["dnameURI", ["uri", "aor"]]]

    #
    # =================== INSTANCE INTERFACE =================================
    #
    @property
    def listenAddress(self):
        lAddr = self._pt_listenAddress
        if lAddr is None:
            raise AttributeError(
                "%r listenAddress is read-only." % (obj.__class__.__name__,))
        return lAddr

    @property
    def inCallDialogs(self):
        """Return a list dialogs that are currently in call. This is only a
        snapshot, and nothing should be assumed about how long the dialogs will
        stay in call for!"""
        try:
            icds = [
                invD
                for invDs in itervalues(self._pt_inviteDialogs)
                for invD in invDs
                if invD.state == invD.States.InDialog]
        except AttributeError as exc:
            log.debug(exc, exc_info=True)
            raise exc
        return icds

    def __init__(self, socketType=None, **kwargs):
        """Create the party.

        :param dnameURI: The display name and URI of this party. To specify
        child components, use underscores to split the path. So to set the AOR
        of the URI, use dnameURI_uri_aor=AOR().
        :param
        """
        super(Party, self).__init__(**kwargs)
        if log.level <= logging.DETAIL:
            log.detail(
                "%r dir after super init: %r", self.__class__.__name__,
                dir(self))

        # Invite dialogs: lists of dialogs keyed by remote AOR.
        self._pt_inviteDialogs = {}
        self._pt_listenAddress = None

        if self.transport is None:
            log.debug("Create new transport for")
            tp = SIPTransport()
            self.transport = tp
            tp.DefaultTransportType = socketType
        log.debug("transport sock type: %s", SockTypeName(
            tp.DefaultTransportType))

        return

    def listen(self):

        uriHost = self.contactURI.aor.host

        contactAddress = uriHost.address
        contactPort = uriHost.port

        if not contactAddress:
            raise ValueError(
                "%r instance has no contact address so cannot listen." % (
                    self.__class__.__name__,))

        uri = self.uri

        log.debug("Listen on %r:%r", contactAddress, contactPort)

        tp = self.transport
        lAddr = tp.listen(lHostName=contactAddress, port=contactPort)
        log.info("Party listening on %r", lAddr)
        self._pt_listenAddress = lAddr
        uriHost.address = lAddr[0]
        uriHost.port = lAddr[1]

        tp.addDialogHandlerForAOR(self.uri.aor, self.newDialogHandler)

    def invite(self, target, proxy=None):

        log.debug("Invite %r proxy %r", target, proxy)
        if not hasattr(self, "uri"):
            raise AttributeError(
                "Cannot build a request since we aren't configured with an "
                "URI!")

        toURI = self._pt_resolveTargetURI(target)
        if proxy is not None:
            assert 0
        else:
            remoteAddress = self._pt_resolveProxyAddress(target)

        invD = self.newInviteDialog(toURI)

        log.debug("Initialize dialog to %r", proxy)
        invD.initiate(remoteAddress=remoteAddress)
        return invD

    def newInviteDialog(self, toURI):
        InviteDialog = self.InviteDialog
        if InviteDialog is None:
            raise AttributeError(
                "Cannot build an INVITE dialog since we aren't configured "
                "with a Dialog Type to use!")

        invD = InviteDialog(
            fromURI=self.uri, toURI=toURI, contactURI=self.contactURI,
            transport=self.transport)

        ids = self._pt_inviteDialogs
        if toURI not in ids:
            ids[toURI] = [invD]
        else:
            ids[toURI].append(invD)

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

    #
    # =================== DELEGATE IMPLEMENTATIONS ===========================
    #
    def scenarioDelegateReset(self):
        log.debug("Resetting after scenario reset.")
        self.myTag = None
        self.theirTag = None

    def newDialogHandler(self, message):
        if message.type == Message.types.invite:
            invD = self.newInviteDialog(
                message.FromHeader.uri)
            invD.receiveMessage(message)
            return
        assert 0

    #
    # =================== MAGIC METHODS ======================================
    #

    #
    # =================== INTERNAL METHODS ===================================
    #
    def _pt_resolveTargetURI(self, target):
        if hasattr(target, "uri"):
            log.debug("Target has a URI to use.")
            return target.uri

        if isinstance(target, URI):
            log.debug("Target is a URI.")
            return target

        if isinstance(target, bytes):
            log.debug("Attempt to parse a URI from the target.")
            return URI.Parse(target)

        raise ValueError("Can't resolve URI from target %r" % (
            target))

    def _pt_resolveProxyAddress(self, target):
        if hasattr(target, "listenAddress"):
            pAddr = target.listenAddress
            if pAddr is not None:
                log.debug("Target has listen address %r", pAddr)
                return pAddr
        assert 0, repr(target)
        if hasattr(target, "contactURI"):
            log.debug("Target has a proxy contact URI.")
            cURI = target.contactURI
            return (cURI.address, cURI.port)

        raise ValueError("Can't resolve proxy from target %r" % (
            target,))

    def _pt_resolveProxyHostFromTarget(self, target):
        try:
            if hasattr(target, "attributeAtPath"):
                for apath in ("contactURI.address", ""):
                    try:
                        tcURI = target.attributeAtPath(apath)
                        return tcURI
                    except AttributeError:
                        pass

            assert 0
        except TypeError:
            raise TypeError(
                "%r instance cannot be derived from %r instance." % (
                    Host.__class__.__name__,
                    target.__class__.__name__))
