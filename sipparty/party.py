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
from six import (binary_type as bytes, itervalues)
from .deepclass import (DeepClass, dck)
from .parse import (ParsedPropertyOfClass)
from .sip import (
    SIPTransport, DNameURI, URI, Host, Request, Message, defaults)
from .transport import (IPaddress_re, IsSpecialName)
from .util import (abytes, WeakMethod)
from .vb import ValueBinder

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
                dck.check: lambda x: IsSpecialName(x) or IPaddress_re.match(x),
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
    DefaultMediaAddress = None

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
            raise
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

        if self.mediaAddress is None:
            self.mediaAddress = self.DefaultMediaAddress

        return

    def listen(self, name=None, port=None, sock_type=None, media_name=None):

        cURI_host = self.contactURI.host
        tp = self.transport
        l_desc = tp.listen_for_me(
            name=name, port=port, sock_type=sock_type)

        cURI_host.address = abytes(l_desc.name)
        cURI_host.port = l_desc.port

        tp.addDialogHandlerForAOR(
            self.uri.aor, WeakMethod(self, "newDialogHandler"))

    def invite(self, target, proxy=None, media_session=None):

        if media_session is not None:
            raise NotImplementedError(
                "Passing a 'media_session' to 'invite' is not yet supported.")

        log.debug("Invite %r proxy %r", target, proxy)
        if not hasattr(self, "uri"):
            raise AttributeError(
                "Cannot build a request since we aren't configured with an "
                "URI!")

        toURI = self._pt_resolveTargetURI(target)
        if proxy is not None:
            assert 0
        else:
            remote_name, remote_port = self._pt_resolveProxyAddress(target)

        invD = self.newInviteDialog(toURI)

        log.debug("Initialize dialog to %r", ((remote_name, remote_port,)))
        invD.initiate(remote_name=remote_name, remote_port=remote_port)
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
        if invD.localSession is not None:
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

        ms = self.__class__.MediaSession(username=b'-')
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
