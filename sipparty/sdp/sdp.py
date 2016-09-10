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
import datetime
import logging
from numbers import Integral
import re
from .. import (parse)
from ..classmaker import classbuilder
from ..util import (abytes, TwoCompatibleThree)
from ..vb import (KeyTransformer, KeyIgnoredExceptions, ValueBinder)
from ..deepclass import (DeepClass, dck)
from .sdpsyntax import (
    NetTypes, AddrTypes, LineTypes, MediaTypes, fmt_space_re,
    AddressToSDPAddrType, bdict, sdp_username_is_ok)

log = logging.getLogger(__name__)
AddrAddrTypeBinding = (
    "address", "addressType", {
        KeyTransformer: lambda x: AddressToSDPAddrType(x),
        KeyIgnoredExceptions: (ValueError,)})


class SDPException(Exception):
    "Base SDP Exception class."


class SDPIncomplete(SDPException):
    "Raised when trying to format SDP that is incomplete."


@TwoCompatibleThree
@classbuilder(bases=(parse.Parser, ValueBinder))
class SDPSection:

    @staticmethod
    def Line(line_type, value):
        if isinstance(value, bytes):
            return b'%s=%s' % (line_type, value)

        if isinstance(value, Integral):
            return b'%s=%d' % (line_type, value)

        if hasattr(value, '__bytes__'):
            return b'%s=%s' % (line_type, bytes(value))

        raise ValueError(
            'Don\'t know how to make bytes out of %r' % value)

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
            b"(%(nettype)s)%(SP)s(%(addrtype)s)%(SP)s(%(address)s)"
            b"" % bdict,
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
            b"%s %s %s" % (self.netType, self.addressType, self.address))


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
            b"%(LineTypes.t)s=(%(start_time)s)%(SP)s(%(stop_time)s)"
            # TODO: Don't ignore repeats and timezone.
            b"(?:%(eol)s%(repeat_fields)s)*%(eol)s"
            b"(?:%(zone_adjustments)s%(eol)s)?"
            b"" % bdict,
        parse.Parser.Mappings:
            [("startTime", int),
             ("stopTime", int)]
    }

    # TODO: Should have repeats as well for completeness.
    def lineGen(self):
        yield self.Line(LineTypes.time, b"%d %d" % (
            self.startTime, self.endTime))


class MediaDescription(
        DeepClass("_mdsc_", {
            "mediaType": {
                dck.check: lambda x: x in MediaTypes},
            "port": {
                dck.check: lambda x: (
                    isinstance(x, Integral) and 0 < x <= 0xffff)},
            "transProto": {},
            "formats": {
                dck.gen: dict
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
            b"%(LineTypes.m)s=(%(media)s)%(SP)s(%(port)s)"
            b"(?:/%(integer)s)?%(SP)s(%(trans_proto)s)%(SP)s"
            b"(%(fmt)s(?:%(SP)s%(fmt)s)*)%(eol)s"
            b"(?:%(LineTypes.i)s=%(text)s%(eol)s)?"
            b"(?:%(LineTypes.c)s=(%(text)s)%(eol)s)?"
            b"(?:%(LineTypes.b)s=%(text)s%(eol)s)*"
            b"(?:%(LineTypes.k)s=%(text)s%(eol)s)?"
            b"(?:%(LineTypes.a)s=%(text)s%(eol)s)*"
            b"" % bdict,
        parse.Parser.Mappings:
            [
                ("mediaType",),
                ("port", int),
                ("transProto",),
                # The standard values for formats are defined in
                # https://tools.ietf.org/html/rfc3551#section-6
                ("formats", lambda fmtstr: [
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
        for attr in ("mediaType", "port", "transProto", "formats"):
            if getattr(self, attr) is None:
                return False
        return True

    def mediaLine(self):
        formats = b' '.join([b'%d' % fmt for fmt in self.formats])
        if len(formats) == 0:
            raise SDPIncomplete(
                "Media description has no format numbers.")
        return self.Line(
            LineTypes.media, b"%s %d %s %s" % (
                self.mediaType, self.port, self.transProto, formats))

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
                dck.check: sdp_username_is_ok},
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
                dck.check: lambda x: x is None or x in AddrTypes,
                dck.get: 'get_address_type'},
            "address": {
                dck.check: lambda x: isinstance(x, bytes),
                dck.get: 'get_address'},
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
            b"%(LineTypes.v)s=%(supportedversions)s%(eol)s"
            # Origin
            b"%(LineTypes.o)s=(%(username)s)%(SP)s(%(sessionid)s)%(SP)s"
            b"(%(sessionversion)s)%(SP)s(%(nettype)s)%(SP)s"
            b"(%(addrtype)s)%(SP)s(%(address)s)%(eol)s"
            # Session name, info, uri, email, phone.
            b"%(LineTypes.s)s=(%(text)s)%(eol)s"
            b"(?:%(LineTypes.i)s=(%(text)s)%(eol)s)?"
            b"(?:%(LineTypes.u)s=(%(text)s)%(eol)s)?"  # TODO: URI.
            b"(?:%(LineTypes.e)s=(%(text)s)%(eol)s)*"  # TODO: email.
            b"(?:%(LineTypes.p)s=(%(text)s)%(eol)s)*"  # TODO: phone.
            # Connection info.
            b"(%(LineTypes.c)s=%(text)s%(eol)s)?"
            # Bandwidth.
            b"(?:%(LineTypes.b)s=(%(text)s)%(eol)s)?"
            # Time.
            b"(%(time_fields)s)"
            # TODO: don't ignore key and attributes.
            b"(?:%(LineTypes.k)s=%(text)s%(eol)s)?"
            b"(?:%(LineTypes.a)s=%(text)s%(eol)s)*"
            b"(%(media_fields)s)"
            b"" % bdict,
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
        return b''

    def get_address_type(self, underlying):
        if underlying is None:
            try:
                return AddressToSDPAddrType(self.address)
            except ValueError:
                return None
        return underlying

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
        ad = self.address
        if ad is None:
            raise SDPIncomplete("No address specified.")
        at = self.addressType
        if at is None:
            raise SDPIncomplete("No address type specified.")
        return self.Line(
            LineTypes.origin,
            b"%s %d %d %s %s %s" % (
                un, self.sessionID, self.sessionVersion, self.netType, at, ad))

    def sessionNameLine(self):
        return self.Line(LineTypes.sessionname, self.sessionName)

    def get_address(self, underlying):
        if underlying is None:
            if self.mediaDescriptions:
                md = self.mediaDescriptions[0]
                return abytes(md.address)

        return underlying

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
