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
import logging
from six import (binary_type as bytes, iteritems)
from ..adapter import AdapterProperty
from ..deepclass import (DeepClass, dck)
from ..sdp import (SessionDescription, MediaDescription)
from ..sdp.mediatransport import MediaTransport
from ..sdp.sdpsyntax import (MediaTypes, sdp_username_is_ok)
from ..transport import (
    IsValidTransportName, ListenDescription, NameLANHostname,
    SOCK_FAMILIES)
from ..util import (FirstListItemProxy, WeakMethod, WeakProperty)
from ..vb import ValueBinder


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
            'username': {dck.check: sdp_username_is_ok},
            'address': {dck.check: IsValidTransportName},
            "transport": {
                dck.gen: MediaTransport
            },
            "mediaSessions": {dck.gen: list},
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

    description = AdapterProperty(SessionDescription)
    mediaSession = FirstListItemProxy('mediaSessions')

    def listen(self, **kwargs):
        if not self.mediaSessions:
            raise NoMediaSessions(
                '%r instance has no media sessions.' % self.__class__.__name__)

        for ms in self.mediaSessions:
            ms.listen(sock_family=self.sock_family)

    def addMediaSession(self, new_med_sess=None, **kwargs):
        """Add a media session to the session.

        NB: This is not thread-safe.
        """
        if new_med_sess is None:
            new_med_sess = MediaSession(**kwargs)
        else:
            if kwargs:
                raise TypeError(
                    'addMediaSession was passed both a new_med_sess and key-'
                    'word args. Only one or the other may be used.')

        # Check that the new media session is compatible with any existing
        # media sessions.
        for curr_med_session in self.mediaSessions:
            for prop in ('name', 'sock_family'):
                cattr = getattr(curr_med_session, prop)
                nattr = getattr(new_med_sess, prop)
                if cattr != nattr:
                    raise ValueError(
                        'Property %r of %r instance %r does not match that of '
                        'the existing media session: %r' % (
                            prop, new_med_sess.__class__.__name__, nattr,
                            cattr))
            break

        self.mediaSession = new_med_sess
        new_med_sess.parent_session = self

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
            },
            'media_type': {dck.check: lambda x: x in MediaTypes},
            'formats': {dck.check: lambda x: isinstance(x, dict)},
            'transProto': {dck.check: lambda x: isinstance(x, str)}
        }),
        ValueBinder):

    vb_dependencies = (
        ('local_addr_description', (
            'name', 'sock_family', 'sock_type', 'port')),
    )

    def listen(self, **local_address_attributes):

        for attr_name, attr_val in iteritems(local_address_attributes):
            setattr(self.local_addr_description, attr_name, attr_val)

        l_desc = self.transport.listen_for_me(
            WeakMethod(self, 'data_received'),
            listen_description=self.local_addr_description
        )
        log.info(
            '%s instance has listen address %s', self.__class__.__name__,
            l_desc)

        self.local_addr_description = l_desc

    def data_received(self, socket_proxy, remote_address_tuple, data):
        assert 0
