"""sdp.py

Code for handling Session Description Protocol

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
import logging
import re
import datetime
from numbers import Integral
from sipparty import (util, vb, parse)
from sipparty.deepclass import (DeepClass, dck)
import sdpsyntax

log = logging.getLogger(__name__)


class SDPException(Exception):
    "Base SDP Exception class."


class SDPIncomplete(SDPException):
    "Raised when trying to format SDP that is incomplete."


@util.TwoCompatibleThree
class SDPSection(parse.Parser, vb.ValueBinder):

    @classmethod
    def Line(cls, lineType, value):
        return b"%s=%s" % (lineType, bytes(value))

    def lineGen(self):
        raise AttributeError(
            "Instance of subclass %r of SDPSection has not implemented "
            "required method 'lineGen'.")

    def __bytes__(self):
        return b"\r\n".join(self.lineGen())


class ConnectionDescription(SDPSection):

    parseinfo = {
        parse.Parser.Pattern:
            b"({nettype}){SP}({addrtype}){SP}({address})"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("_cd_netType",),
             ("_cd_addrType",),
             ("_cd_address",)],
    }

    netType = util.DerivedProperty(
        "_cd_netType", lambda x: x in sdpsyntax.NetTypes)
    addrType = util.DerivedProperty(
        "_cd_addrType", lambda x: x in sdpsyntax.AddrTypes)
    address = util.DerivedProperty(
        "_cd_address", lambda x: isinstance(x, bytes))

    def __init__(self, netType=None, addrType=None, address=None):
        super(ConnectionDescription, self).__init__()

        self.netType = (netType if netType is not None else
                        sdpsyntax.NetTypes.IN)
        if addrType is not None:
            self.addrType = addrType
        else:
            self._cd_addrType = None
        if address is not None:
            self.address = address
        else:
            self._cd_address = None

    def lineGen(self):
        """c=<nettype> <addrtype> <connection-address>"""
        if self.addrType is None:
            raise SDPIncomplete("Connection description has no address type.")
        if self.address is None:
            raise SDPIncomplete("Connection description has no address set.")
        yield self.Line(
            sdpsyntax.LineTypes.connectioninfo,
            "%s %s %s" % (self.netType, self.addrType, self.address))


class TimeDescription(SDPSection):

    #
    # =================== CLASS INTERFACE =====================================
    #
    parseinfo = {
        parse.Parser.Pattern:
            b"{LineTypes.time}=({start_time}){SP}({stop_time})"
            # TODO: Don't ignore repeats and timezone.
            "(?:{eol}{repeat_fields})*{eol}"
            "(?:{zone_adjustments}{eol})?"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("_td_startTime", int),
             ("_td_stopTime", int)]
    }

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    startTime = util.DerivedProperty(
        "_td_startTime", lambda x: isinstance(x, Integral))
    endTime = util.DerivedProperty(
        "_td_endTime", lambda x: isinstance(x, Integral))

    def __init__(self, startTime=None, endTime=None):
        super(TimeDescription, self).__init__()

        self.startTime = (startTime
                          if startTime is not None
                          else 0)
        self.endTime = (endTime
                        if endTime is not None
                        else 0)

        # TODO: Should have repeats as well for completeness.

    def lineGen(self):
        yield self.Line(sdpsyntax.LineTypes.time, "%d %d" % (
            self.startTime, self.endTime))


class MediaDescription(SDPSection):

    #
    # =================== CLASS INTERFACE =====================================
    #
    parseinfo = {
        parse.Parser.Pattern:
            b"{LineTypes.media}=({media}){SP}({port})(?:/{integer})?{SP}"
            "({proto}){SP}({fmt}(?:{SP}{fmt})*){eol}"
            "(?:{LineTypes.info}={text}{eol})?"
            "(?:{LineTypes.connectioninfo}=({text}){eol})?"
            "(?:{LineTypes.bandwidthinfo}={text}{eol})*"
            "(?:{LineTypes.encryptionkey}={text}{eol})?"
            "(?:{LineTypes.attribute}={text}{eol})*"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("_md_mediaType",),
             ("_md_port", int),
             ("_md_proto",),
             ("_md_fmt",),
             ("_md_connectionDescription", ConnectionDescription)],
        parse.Parser.Repeats: True
    }

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    mediaType = util.DerivedProperty(
        "_md_mediaType", lambda x: x in sdpsyntax.MediaTypes)
    port = util.DerivedProperty(
        "_md_port",
        lambda x: isinstance(x, Integral) and 0 < x <= 0xffff)
    proto = util.DerivedProperty("_md_proto")
    fmt = util.DerivedProperty("_md_fmt")
    connectionDescription = util.DerivedProperty("_md_connectionDescription")

    def __init__(
            self, mediaType=None, port=None, proto=None, fmt=None,
            connectionDescription=None):
        super(MediaDescription, self).__init__()

        for unguessable_attribute in ("mediaType", "port", "proto", "fmt"):
            val = locals()[unguessable_attribute]
            if val is None:
                setattr(self, "_md_" + unguessable_attribute, val)
            else:
                # This gives us the type checking of DerivedProperty.
                setattr(self, unguessable_attribute, val)

        self.connectionDescription = connectionDescription

    def setConnectionDescription(self, **kwargs):
        self.connectionDescription = ConnectionDescription(**kwargs)

    def mediaLine(self):
        for attr in ("mediaType", "port", "proto", "fmt"):
            if getattr(self, attr) is None:
                raise SDPIncomplete(
                    "Required media attribute %r not specified." % (attr,))
        return self.Line(
            sdpsyntax.LineTypes.media, "%s %s %s %s" % (
                self.mediaType, self.port, self.proto, self.fmt))

    def lineGen(self):
        """m=<media> <port> <proto> <fmt> ..."""
        yield self.mediaLine()
        if self.connectionDescription is not None:
            for ln in self.connectionDescription.lineGen():
                yield ln


class SessionDescription(
        DeepClass("_sdsc_", {
            "username": {
                dck.check: lambda x: sdpsyntax.username_re.match(x)},
            "sessionID": {
                dck.check: lambda x: isinstance(x, Integral),
                dck.gen: "ID"},
            "sessionVersion": {
                dck.check: lambda x: isinstance(x, Integral),
                dck.gen: "ID"},
            "netType": {
                dck.check: lambda x: x in sdpsyntax.NetTypes,
                dck.gen: lambda: sdpsyntax.NetTypes.IN},
            "addrType": {dck.check: lambda x: x in sdpsyntax.AddrTypes},
            "address": {dck.check: lambda x: isinstance(x, bytes)},
            "sessionName": {
                dck.check: lambda x: isinstance(x, bytes),
                dck.gen: lambda: b" "},
            "connectionDescription": {
                dck.check: lambda x: isinstance(x, ConnectionDescription),
                dck.gen: ConnectionDescription},
            "timeDescription": {
                dck.check: lambda x: isinstance(x, TimeDescription),
                dck.gen: TimeDescription},
            "mediaDescriptions": {dck.gen: list},
        }),
        SDPSection):
    """SDP is made of 3 sections:

    Session Description (one)
    Time Description (one)
    Media Description (one or more)

    The SDP spec says something about multiple session descriptions, but I'm
    making the initial assumption that in SIP there will only be one.
    """
    #
    # =================== CLASS INTERFACE =====================================
    #
    parseinfo = {
        parse.Parser.Pattern:
            # Version
            "{LineTypes.version}={supportedversions}{eol}"
            # Origin
            "{LineTypes.origin}=({username}){SP}({sessionid}){SP}"
            "({sessionversion}){SP}({nettype}){SP}({addrtype}){SP}"
            "({address}){eol}"
            # Session name, info, uri, email, phone.
            "{LineTypes.sessionname}=({text}){eol}"
            "(?:{LineTypes.info}=({text}){eol})?"
            "(?:{LineTypes.uri}=({text}){eol})?"  # TODO: URI.
            "(?:{LineTypes.email}=({text}){eol})*"  # TODO: email.
            "(?:{LineTypes.phone}=({text}){eol})*"  # TODO: phone.
            # Connection info.
            "({LineTypes.connectioninfo}={text}{eol})?"
            # Bandwidth.
            "(?:{LineTypes.bandwidthinfo}=({text}){eol})?"
            # Time.
            "({time_fields})"
            # TODO: don't ignore key and attributes.
            "(?:{LineTypes.encryptionkey}={text}{eol})?"
            "(?:{LineTypes.attribute}={text}{eol})*"
            "({media_fields})"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("username",),
             ("sessionID", int),
             ("sessionVersion", int),
             ("netType",),
             ("addrType",),
             ("address",),
             ("sessionName",),
             ("info",),
             ("uri",),
             ("email",),
             ("phone",),
             ("connectionDescription", ConnectionDescription),
             ("bandwidth",),
             ("timeDescription", TimeDescription),
             ("mediaDescriptions", MediaDescription)]
    }

    username_pattern = re.compile("\S+")

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
    @classmethod
    def EmptyLine(cls):
        return b""

    def addMediaDescription(self, **kwargs):

        md = MediaDescription(**kwargs)
        self.mediaDescriptions.append(md)

    def versionLine(self):
        "v=0"
        return self.Line(sdpsyntax.LineTypes.version, 0)

    def originLine(self):
        """o=<username> <sess-id> <sess-version> <nettype> <addrtype>
        <unicast-address>
        """
        un = self.username
        if un is None:
            raise SDPIncomplete("No username specified.")
        at = self.addrType
        if at is None:
            raise SDPIncomplete("No address type specified.")
        ad = self.address
        if ad is None:
            raise SDPIncomplete("No address specified.")
        return self.Line(
            sdpsyntax.LineTypes.origin,
            b"%s %d %d %s %s %s" % (
                un, self.sessionID, self.sessionVersion, self.netType, at, ad))

    def sessionNameLine(self):
        return self.Line(sdpsyntax.LineTypes.sessionname, self.sessionName)

    def lineGen(self):
        """v=0
        o=<username> <sess-id> <sess-version> <nettype> <addrtype>
        <unicast-address>
        """
        yield self.versionLine()
        yield self.originLine()
        yield self.sessionNameLine()
        if self.connectionDescription is None:
            if len(self.mediaDescriptions) == 0:
                raise SDPIncomplete(
                    "SDP has no connection description and no media "
                    "descriptions.")
            for md in self.mediaDescriptions:
                if md.connectionDescription is None:
                    raise SDPIncomplete(
                        "SDP has no connection description and not all media "
                        "descriptions have one.")
        for ln in self.timeDescription.lineGen():
            yield ln
        for md in self.mediaDescriptions:
            for ln in md.lineGen():
                yield ln
        yield self.EmptyLine()
