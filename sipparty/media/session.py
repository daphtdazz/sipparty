"""session.py

A media session.

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
import datetime
import logging
import re
from six import (binary_type as bytes)
from ..deepclass import (DeepClass, dck)
from ..sdp import (SessionDescription, MediaDescription)
from ..sdp.mediatransport import MediaTransport
from ..sdp.sdpsyntax import (username_re, AddrTypes)
from ..transport import (
    IsValidTransportName, ListenDescription, NameLANHostname, SOCK_FAMILIES)
from ..util import (abytes, FirstListItemProxy, WeakMethod, WeakProperty)
from ..vb import (KeyTransformer, ValueBinder)

log = logging.getLogger(__name__)


class MediaSessionError(Exception):
    pass


class NoMediaSessions(MediaSessionError):
    pass


def MediaSessionListenDescription():
    # Media sessions need to listen on even ports, so the RTCP port is on one
    # above.
    return ListenDescription(port_filter=lambda pt: pt % 2 == 0)


class Session(
        DeepClass("_sess_", {
            "transport": {
                dck.gen: MediaTransport
            },
            "description": {
                dck.check: lambda x: isinstance(x, SessionDescription),
                dck.gen: SessionDescription},
            "mediaSessions": {dck.gen: list},

            "name": {
                dck.check: lambda x: IsValidTransportName(x)
            },
            'sock_family': {dck.check: lambda x: x in SOCK_FAMILIES}
        }),
        ValueBinder):
    """Implements a media session, with ways of playing media and creation of
    SDP. Strictly this is independent of SDP, but in practice its form is
    heavily informed by SDP's, so if someone wants to write a different
    protocol for transporting SDP this might need some tweaking, but come on
    that's never going to happen.

    SDP is defined in http://www.ietf.org/rfc/rfc4566.txt, which this duly
    follows.
    """
    DefaultName = NameLANHostname

    vb_dependencies = (
        ("description", ("username", "address", "addressType")),)
    vb_bindings = (
        ('name', 'description.address', {KeyTransformer: abytes}),
    )
    mediaSession = FirstListItemProxy("mediaSessions")

    def listen(self, **kwargs):
        if not self.mediaSessions:
            raise NoMediaSessions(
                '%r instance has no media sessions.' % self.__class__.__name__)

        for ms in self.mediaSessions:
            name = self.name or self.DefaultName
            ms.listen()

    def addMediaSession(self, mediaSession=None, **kwargs):
        if mediaSession is None:
            mediaSession = MediaSession(**kwargs)
        else:
            if kwargs:
                raise TypeError(
                    'addMediaSession was passed both a mediaSession and key-'
                    'word args. Only one or the other may be used.')
        self.mediaSessions.insert(0, mediaSession)
        self.description.addMediaDescription(mediaSession.description)
        mediaSession.parent_session = self
        mediaSession.name = self.name
        mediaSession.sock_family = self.sock_family

    def sdp(self):
        return bytes(self.description)


class MediaSession(
        DeepClass("_msess_", {
            'parent_session': {
                dck.descriptor: WeakProperty
            },
            "transport": {
                dck.gen: MediaTransport
            },
            "description": {
                dck.check: lambda x: isinstance(x, MediaDescription),
                dck.gen: MediaDescription},
            'local_addr_description': {
                dck.gen: MediaSessionListenDescription,
            }
        }),
        ValueBinder):
    vb_dependencies = (
        ("description", (
            "mediaType", "port", "address", "addressType", "transProto",
            "fmts")),)

    def listen(self):

        l_desc = self.transport.listen_for_me(
            WeakMethod(self, 'data_received'),
            listen_description=self.local_addr_description
            )
        log.error('Media listen address: %r', l_desc)

        #TODO: this is wrong.
        self.address = abytes(l_desc.name)
        self.port = l_desc.port
        return l_desc

    def data_received(self, socket_proxy, remote_address_tuple, data):
        assert 0
