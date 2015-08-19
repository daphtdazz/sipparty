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
import logging
import six
import re
import datetime
from sipparty import (parse,)
from sipparty.util import (FirstListItemProxy,)
from sipparty.vb import ValueBinder
from sipparty.deepclass import (DeepClass, dck)
from sipparty.sdp import (SessionDescription, MediaDescription)
from sipparty.sdp.sdpsyntax import (username_re,)

log = logging.getLogger(__name__)
bytes = six.binary_type


class Session(
        DeepClass("_sess_", {
            "transport": {},
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
        assert 0

    def addMediaSession(self, **kwargs):
        nms = MediaSession(**kwargs)
        self.mediaSessions.insert(0, nms)
        self.description.addMediaDescription(nms.description)

    def sdp(self):
        return bytes(self.description)


class MediaSession(
        DeepClass("_msess_", {
            "transport": {},
            "description": {
                dck.check: lambda x: isinstance(x, MediaDescription),
                dck.gen: MediaDescription},
        }),
        ValueBinder):
    vb_dependencies = (
        ("description", ("mediaType", "port", "addressType", "proto", "fmt")),)


class RTPMediaSession(MediaSession):
    """An session."""
