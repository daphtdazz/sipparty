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
from sipparty import (util, parse)
from sipparty.vb import (KeyTransformer, KeyIgnoredExceptions, ValueBinder)
from sipparty.deepclass import (DeepClass, dck)
import sdpsyntax
from sdpsyntax import (
    NetTypes, AddrTypes, LineTypes, MediaTypes, username_re, fmt_space_re,
    AddressToSDPAddrType)

log = logging.getLogger(__name__)
AddrAddrTypeBinding = (
    "address", "addressType", {
        KeyTransformer: lambda x: AddressToSDPAddrType(x),
        KeyIgnoredExceptions: (ValueError,)})


class SDPException(Exception):
    "Base SDP Exception class."


class SDPIncomplete(SDPException):
    "Raised when trying to format SDP that is incomplete."


@util.TwoCompatibleThree
class SDPSection(parse.Parser, ValueBinder):

    @classmethod
    def Line(cls, lineType, value):
        return b"%s=%s" % (lineType, bytes(value))

    def lineGen(self):
        raise AttributeError(
            "Instance of subclass %r of SDPSection has not implemented "
            "required method 'lineGen'.")

    @property
    def isComplete(self):
        return True

    def __bytes__(self):
        return b"\r\n".join(self.lineGen())


class ConnectionDescription(
        DeepClass("_cdsc_", {
            "netType": {
                dck.check: lambda x: x in NetTypes,
                dck.gen: lambda: NetTypes.IN},
            "addressType": {
                dck.check: lambda x: x is None or x in AddrTypes},
            "address": {dck.check: lambda x: isinstance(x, bytes)},
        }),
        SDPSection):

    vb_bindings = (
        AddrAddrTypeBinding,)

    parseinfo = {
        parse.Parser.Pattern:
            b"({nettype}){SP}({addrtype}){SP}({address})"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("netType",),
             ("addressType",),
             ("address",)],
    }

    @property
    def isComplete(self):
        return self.address is not None and self.address is not None

    def lineGen(self):
        """c=<nettype> <addressType> <connection-address>"""
        if not self.isComplete:
            raise SDPIncomplete(
                "Connection description is not complete: %r." % self)
        yield self.Line(
            LineTypes.connectioninfo,
            "%s %s %s" % (self.netType, self.addressType, self.address))


class TimeDescription(
        DeepClass("_td_", {
            "startTime": {
                dck.check: lambda x: isinstance(x, Integral),
                dck.gen: lambda: 0},
            "endTime": {
                dck.check: lambda x: isinstance(x, Integral),
                dck.gen: lambda: 0}
        }),
        SDPSection):

    parseinfo = {
        parse.Parser.Pattern:
            b"{LineTypes.time}=({start_time}){SP}({stop_time})"
            # TODO: Don't ignore repeats and timezone.
            "(?:{eol}{repeat_fields})*{eol}"
            "(?:{zone_adjustments}{eol})?"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("startTime", int),
             ("stopTime", int)]
    }

    # TODO: Should have repeats as well for completeness.
    def lineGen(self):
        yield self.Line(LineTypes.time, "%d %d" % (
            self.startTime, self.endTime))


class MediaDescription(
        DeepClass("_mdsc_", {
            "mediaType": {
                dck.check: lambda x: x in MediaTypes},
            "port": {
                dck.check: lambda x: (
                    isinstance(x, Integral) and 0 < x <= 0xffff)},
            "transProto": {},
            "fmts": {
                dck.gen: list
            },
            "connectionDescription": {
                dck.check: lambda x: isinstance(x, ConnectionDescription),
                dck.gen: ConnectionDescription}
        }),
        SDPSection):

    #
    # =================== CLASS INTERFACE =====================================
    #
    parseinfo = {
        parse.Parser.Pattern:
            b"{LineTypes.media}=({media}){SP}({port})(?:/{integer})?{SP}"
            "({trans_proto}){SP}({fmt}(?:{SP}{fmt})*){eol}"
            "(?:{LineTypes.info}={text}{eol})?"
            "(?:{LineTypes.connectioninfo}=({text}){eol})?"
            "(?:{LineTypes.bandwidthinfo}={text}{eol})*"
            "(?:{LineTypes.encryptionkey}={text}{eol})?"
            "(?:{LineTypes.attribute}={text}{eol})*"
            "".format(**sdpsyntax.__dict__),
        parse.Parser.Mappings:
            [("mediaType",),
             ("port", int),
             ("transProto",),
             # The standard values for formats are defined in
             # https://tools.ietf.org/html/rfc3551#section-6
             ("fmts", lambda fmtstr: [
                int(fmt) for fmt in fmt_space_re.split(fmtstr)]),
             ("connectionDescription", ConnectionDescription)],
        parse.Parser.Repeats: True
    }

    vb_dependencies = (
        ("connectionDescription", ("addressType", "netType", "address")),)
    vb_bindings = (
        AddrAddrTypeBinding,)

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    @property
    def isComplete(self):
        for attr in ("mediaType", "port", "transProto", "fmts"):
            if getattr(self, attr) is None:
                return False
        return True

    def mediaLine(self):
        fmts = b' '.join([bytes(str(fmt)) for fmt in self.fmts])
        if len(fmts) == 0:
            raise SDPIncomplete(
                "Media description has no format numbers.")
        return self.Line(
            LineTypes.media, "%s %s %s %s" % (
                self.mediaType, self.port, self.transProto, fmts))

    def lineGen(self):
        """m=<media> <port> <transProto> <fmt> ..."""
        if not self.isComplete:
            raise SDPIncomplete(
                "Media description incomplete: %r" % (self,))
        yield self.mediaLine()
        if (self.connectionDescription is not None and
                self.connectionDescription.isComplete):
            for ln in self.connectionDescription.lineGen():
                yield ln


class SessionDescription(
        DeepClass("_sdsc_", {
            "username": {
                dck.check: lambda x: username_re.match(x)},
            "sessionID": {
                dck.check: lambda x: isinstance(x, Integral),
                dck.gen: "ID"},
            "sessionVersion": {
                dck.check: lambda x: isinstance(x, Integral),
                dck.gen: "ID"},
            "netType": {
                dck.check: lambda x: x in NetTypes,
                dck.gen: lambda: NetTypes.IN},
            "addressType": {
                dck.check: lambda x: x is None or x in AddrTypes},
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
             ("addressType",),
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

    vb_bindings = (
        ("address", "connectionDescription.address"),
        AddrAddrTypeBinding)

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

    def addMediaDescription(self, md=None, **kwargs):

        if md is None:
            md = MediaDescription(**kwargs)
        self.mediaDescriptions.append(md)

    def versionLine(self):
        "v=0"
        return self.Line(LineTypes.version, 0)

    def originLine(self):
        """o=<username> <sess-id> <sess-version> <nettype> <addressType>
        <unicast-address>
        """
        un = self.username
        if un is None:
            raise SDPIncomplete("No username specified.")
        at = self.addressType
        if at is None:
            raise SDPIncomplete("No address type specified.")
        ad = self.address
        if ad is None:
            raise SDPIncomplete("No address specified.")
        return self.Line(
            LineTypes.origin,
            b"%s %d %d %s %s %s" % (
                un, self.sessionID, self.sessionVersion, self.netType, at, ad))

    def sessionNameLine(self):
        return self.Line(LineTypes.sessionname, self.sessionName)

    def lineGen(self):
        """v=0
        o=<username> <sess-id> <sess-version> <nettype> <addressType>
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
