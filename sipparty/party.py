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
    SIPTransport, DNameURI, URI, Host, Incomplete, Request, Message, defaults)
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
            "display_name_uri": {
                dck.descriptor: ParsedPropertyOfClass(DNameURI),
                dck.gen: DNameURI},
            "contact_uri": {
                dck.descriptor: ParsedPropertyOfClass(URI),
                dck.gen: URI},
            "mediaAddress": {
                dck.check: lambda x: IsSpecialName(x) or IPaddress_re.match(x),
                dck.get: lambda self, underlying: (
                    underlying if underlying is not None else
                    self.contact_uri.address)
            },
            "transport": {dck.gen: SIPTransport}
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
        ("display_name_uri", ("uri", "aor")),)

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

    def __init__(self, display_name_uri=None, **kwargs):
        """Create the party.

        :param display_name_uri: The display name and URI of this party.
        """
        super(Party, self).__init__(
            display_name_uri=display_name_uri, **kwargs)
        if log.level <= logging.DETAIL:
            log.detail(
                "%r dir after super init: %r", self.__class__.__name__,
                dir(self))

        # Invite dialogs: lists of dialogs keyed by remote AOR.
        self._pt_inviteDialogs = {}
        self._pt_listenAddress = None

        if self.mediaAddress is None:
            self.mediaAddress = self.DefaultMediaAddress

        return

    def listen(self, **kwargs):

        aor = self.uri.aor
        try:
            bytes(aor)
        except Incomplete as exc:
            exc.args = (
                "Party instance can't listen as it has an incomplete uri",
            )
            raise

        tp = self.transport
        tp.addDialogHandlerForAOR(
            self.uri.aor, WeakMethod(self, 'newDialogHandler'))

        cURI_host = self.contact_uri.host
        l_desc = tp.listen_for_me(**kwargs)

        cURI_host.address = abytes(l_desc.name)
        cURI_host.port = l_desc.port

    def invite(self, target, proxy=None, media_session=None):

        if media_session is not None:
            raise NotImplementedError(
                "Passing a 'media_session' to 'invite' is not yet supported.")

        log.debug("Invite %r proxy %r", target, proxy)
        if not hasattr(self, "uri"):
            raise AttributeError(
                "Cannot build a request since we aren't configured with an "
                "URI!")

        to_uri = self._pt_resolveTargetURI(target)
        if proxy is not None:
            assert 0
        else:
            remote_name, remote_port = self._pt_resolveProxyAddress(target)

        invD = self.newInviteDialog(to_uri)

        log.debug("Initialize dialog to %r", ((remote_name, remote_port,)))
        invD.initiate(remote_name=remote_name, remote_port=remote_port)
        return invD

    def newInviteDialog(self, to_uri):
        InviteDialog = self.InviteDialog
        if InviteDialog is None:
            raise AttributeError(
                "Cannot build an INVITE dialog since we aren't configured "
                "with a Dialog Type to use!")

        invD = InviteDialog(
            from_uri=self.uri, to_uri=to_uri,
            contact_uri=self.contact_uri,
            transport=self.transport)
        invD.localSession = self.newSession()

        ids = self._pt_inviteDialogs
        if to_uri not in ids:
            ids[to_uri] = [invD]
        else:
            ids[to_uri].append(invD)

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

    @staticmethod
    def _pt_check_address_tuple(_tuple):
        return not any(val is None for val in _tuple)

    def _pt_resolveProxyAddress(self, target):
        if hasattr(target, "listenAddress"):
            pAddr = target.listenAddress
            if pAddr is not None:
                log.debug("Target has listen address %r", pAddr)
                return pAddr

        if hasattr(target, "contact_uri"):
            log.debug("Target has a proxy contact URI.")
            cURI = target.contact_uri
            rtup = (cURI.address, cURI.port)
            if not self._pt_check_address_tuple(rtup):
                raise ValueError(
                    "Target's contact URI is not complete: %r" % cURI)
            return rtup

        try:
            turi = self._pt_resolveTargetURI(target)
        except (TypeError, ValueError) as exc:
            raise type(exc)("Can't resolve proxy from target %r" % (
                target,))

        rtup = (turi.address, turi.port)
        if not self._pt_check_address_tuple(rtup):
            raise ValueError("Target URI is not complete: %r" % (turi,))

        return rtup

    def _pt_resolveProxyHostFromTarget(self, target):
        try:
            if hasattr(target, "attributeAtPath"):
                for apath in ("contact_uri.address", ""):
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
