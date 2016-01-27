"""sessions.py

Cookie-cutter sessions.

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
from ..sdp.sdpsyntax import (MediaTypes, MediaProtocols)
from ..media.session import (Session, MediaSession)
from ..util import astr


class SingleRTPSession(Session):
    def __init__(self, **kwargs):
        super(SingleRTPSession, self).__init__(**kwargs)
        ms = RTPPCMUMediaSession()
        self.addMediaSession(ms)


class RTPPCMUMediaSession(MediaSession):
    def __init__(self, **kwargs):
        super(RTPPCMUMediaSession, self).__init__(**kwargs)
        self.mediaType = MediaTypes.audio
        self.transProto = astr(MediaProtocols.RTP_AVP)
        self.fmts = [0]
