"""mediasession.py

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
from ..util import (abytes, FirstListItemProxy,)
from ..vb import ValueBinder

log = logging.getLogger(__name__)


class Session(
        DeepClass("_sess_", {
            "transport": {
                dck.gen: MediaTransport
            },
            "description": {
                dck.check: lambda x: isinstance(x, SessionDescription),
                dck.gen: SessionDescription},
            "mediaSessions": {dck.gen: list},
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
    vb_dependencies = (
        ("description", ("username", "address", "addressType")),)
    mediaSession = FirstListItemProxy("mediaSessions")

    def listen(self):
        for ms in self.mediaSessions:
            ms.listen(self.address)

    def addMediaSession(self, mediaSession=None, **kwargs):
        if mediaSession is None:
            mediaSession = MediaSession(**kwargs)
        self.mediaSessions.insert(0, mediaSession)
        self.description.addMediaDescription(mediaSession.description)

    def sdp(self):
        return bytes(self.description)


class MediaSession(
        DeepClass("_msess_", {
            "transport": {
                dck.gen: MediaTransport
            },
            "description": {
                dck.check: lambda x: isinstance(x, MediaDescription),
                dck.gen: MediaDescription},
        }),
        ValueBinder):
    vb_dependencies = (
        ("description", (
            "mediaType", "port", "address", "addressType", "transProto",
            "fmts")),)

    def listen(self, session_address):
        if hasattr(self, "address"):
            lAddr = self.address
        else:
            lAddr = session_address

        lAddrTuple = self.transport.listen(
            lHostName=lAddr, port_filter=lambda pt: pt % 2 == 0)

        self.address = abytes(lAddrTuple[0])
        self.port = lAddrTuple[1]
        return lAddrTuple
