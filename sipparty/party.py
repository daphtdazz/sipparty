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
import logging
import socket
from six import (binary_type as bytes, itervalues)
from .deepclass import (DeepClass, dck)
from .media import (Session, MediaSession)
from .parse import (ParsedPropertyOfClass)
from .sdp import sdpsyntax
from .sip import (
    SIPTransport, Incomplete, DNameURI, AOR, URI, Host, Request, Message,
    Body, defaults)
from .transport import (SockTypeName, IPaddress_re)
from .util import (abytes, DerivedProperty, WeakMethod)
from .vb import ValueBinder

__all__ = ('Party', 'PartySubclass')

log = logging.getLogger(__name__)


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


class Party(
        DeepClass("_pt_", {
            "dnameURI": {
                dck.descriptor: ParsedPropertyOfClass(DNameURI),
                dck.gen: DNameURI},
            "contactURI": {
                dck.descriptor: ParsedPropertyOfClass(URI),
                dck.gen: URI},
            "mediaAddress": {
                dck.check: lambda x: IPaddress_re.match(x),
                dck.get: lambda self, underlying: (
                    underlying if underlying is not None else
                    self.contactURI.address)
            },
            "transport": {dck.gen: lambda: None}
        }),
        ValueBinder):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    #
    # =================== CLASS INTERFACE ====================================
    #
    InviteDialog = None
    MediaSession = None

    vb_dependencies = (
        ("dnameURI", ("uri", "aor")),)

    #
    # =================== INSTANCE INTERFACE =================================
    #
    @property
    def listenAddress(self):
        lAddr = self._pt_listenAddress
        if lAddr is None:
            raise AttributeError(
                "%r no listen address." % (self.__class__.__name__,))
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

    def __init__(self, dnameURI=None, **kwargs):
        """Create the party.

        :param dnameURI: The display name and URI of this party. To specify
        child components, use underscores to split the path. So to set the AOR
        of the URI, use dnameURI_uri_aor=AOR().
        :param
        """
        super(Party, self).__init__(dnameURI=dnameURI, **kwargs)
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

        if self.contactURI.address is None:
            self.contactURI.address = abytes(socket.gethostname())

        return

    def listen(self, address_name=None):

        if address_name is not None:
            self.contactURI.address = abytes(address_name)

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
        lAddr = tp.listen(name=contactAddress, port=contactPort)
        assert lAddr[1] != 0
        log.info("Party listening on %r", lAddr)
        self._pt_listenAddress = lAddr
        uriHost.address = abytes(lAddr[0])
        uriHost.port = lAddr[1]

        tp.addDialogHandlerForAOR(
            self.uri.aor, WeakMethod(self, "newDialogHandler"))

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
        invD.localSession = self.newSession()
        invD.localSession.listen()

        ids = self._pt_inviteDialogs
        if toURI not in ids:
            ids[toURI] = [invD]
        else:
            ids[toURI].append(invD)

        invD.delegate = self

        return invD

    def newSession(self):
        MS = self.MediaSession
        if MS is None:
            log.debug(
                "No media session configured for %r instance.",
                self.__class__.__name__)
            return None

        ma = self.mediaAddress
        ms = self.__class__.MediaSession(username=b'-', address=ma)
        return ms

    #
    # =================== DELEGATE IMPLEMENTATIONS ===========================
    #
    def newDialogHandler(self, message):
        if message.type == Message.types.invite:
            invD = self.newInviteDialog(
                message.FromHeader.uri)
            invD.receiveMessage(message)
            return
        assert 0

    def configureOutboundMessage(self, message):

        if message.type == Request.types.invite:
            self._pt_configureInvite(message)

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

        raise ValueError("Can't resolve URI from target %r" % (target))

    def _pt_resolveProxyAddress(self, target):
        if hasattr(target, "listenAddress"):
            pAddr = target.listenAddress
            if pAddr is not None:
                log.debug("Target has listen address %r", pAddr)
                return pAddr

        if hasattr(target, "contactURI"):
            log.debug("Target has a proxy contact URI.")
            cURI = target.contactURI
            return (cURI.address, cURI.port)

        try:
            turi = self._pt_resolveTargetURI(target)
        except (TypeError, ValueError) as exc:
            raise type(exc)("Can't resolve proxy from target %r" % (
                target,))
        return (turi.address, turi.port)

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

    def _pt_configureInvite(self, inv):
        pass
