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
import vb
import _util

log = logging.getLogger(__name__)
bytes = six.binary_type


class MediaSession(vb.ValueBinder):
    """Implements a media session, with ways of playing media and creation of
    SDP. Strictly this is independent of SDP, but in practice its form is
    heavily informed by SDP's, so if someone wants to write a different
    protocol for transporting SDP this might need some tweaking, but come on
    that's never going to happen.

    SDP is defined in http://www.ietf.org/rfc/rfc4566.txt, which this duly
    follows.
    """

    #
    # =================== CLASS INTERFACE =====================================
    #
    NetTypes = _util.Enum(("IN",))
    AddrTypes = _util.Enum(("IP4", "IP6"))

    @classmethod
    def ID(cls):
        if not hasattr(cls, "_MS_epochTime"):
            cls._MS_epochTime = datetime.datetime(1900, 1, 1, 0, 0, 0)
        et = cls._MS_epochTime
        diff = datetime.datetime.utcnow() - et
        return diff.days * 24 * 60 * 60 + diff.seconds

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    username_pattern = re.compile("\S+")
    username = _util.DerivedProperty(
        "_ms_username",
        lambda x: x is None or MediaSession.username_pattern.match(x))
    sessionID = _util.DerivedProperty(
        "_ms_sessionID", lambda x: isinstance(x, int))
    sessionVersion = _util.DerivedProperty(
        "_ms_sessionVersion", lambda x: isinstance(x, int))
    netType = _util.DerivedProperty(
        "_ms_netType", lambda x: x in MediaSession.NetTypes)
    addrType = _util.DerivedProperty(
        "_ms_addrType", lambda x: x in MediaSession.AddrTypes)
    name = _util.DerivedProperty(
        "_ms_sessionName",
        lambda x: x is None or isinstance(x, bytes))

    def __init__(self, username=None, sessionID=None, sessionVersion=None,
                 netType=None, name=None):
        super(MediaSession, self).__init__()

        self.username = username
        self.name = name

        if sessionID is None:
            sessionID = MediaSession.ID()
        self.sessionID = sessionID
        if sessionVersion is None:
            sessionVersion = MediaSession.ID()
        self.sessionVersion = sessionVersion
        if netType is None:
            netType = MediaSession.NetTypes.IN
        self.netType = netType
