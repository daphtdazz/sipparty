"""sdpsyntax.py

This module contains details on SDP's syntax from RFC4566.

Note that for python2/3 compatibility all SIP messages use `bytes` not `str`
(although obviously `bytes` is `str` in python 2).

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
import re
from socket import (AF_INET, AF_INET6)
from ..transport import (IPv4address_only_re, IPv6address_only_re)
from ..util import (abytes, AsciiBytesEnum, bglobals_g)


def bglobals():
    return bglobals_g(globals())

NetTypes = AsciiBytesEnum((b"IN",))
AddrTypes = AsciiBytesEnum((b"IP4", b"IP6"))
MediaTypes = AsciiBytesEnum((
    b"audio", b"video", b"text", b"application", b"message"))
LineTypes = AsciiBytesEnum(
    aliases={
        b"version": b"v",
        b"origin": b"o",
        b"sessionname": b"s",
        b"info": b"i",
        b"uri": b"u",
        b"email": b"e",
        b"phone": b"p",
        b"connectioninfo": b"c",
        b"bandwidthinfo": b"b",
        b"time": b"t",
        b"repeat": b"r",
        b"timezone": b"z",
        b"encryptionkey": b"k",
        b"attribute": b"a",
        b"media": b"m"
    })

DIGIT = b"\d"
number = b"%(DIGIT)s+" % bglobals()
SP = b"\x20"
space = SP
VCHAR = b"\x21-\x7e"
eol = b"\r?\n"
token_char = b"[\x21\x23-\x27\x2a\x2b\x2d\x2e\x30-\x39\x41-\x5a\x5e-\x7e]"
token = b"%(token_char)s+" % bglobals()

supportedversions = b"0"

non_ws_string = b"[%(VCHAR)s\x80-\xff]+" % bglobals()
text = b"[^\x00\x0a\x0d]+"
integer = b"[1-9]\d*"
time = b"[1-9][0-9]{9,}"
time_or_zero = b"(?:0|%(time)s)" % bglobals()
fixed_len_time_unit = b"[dhms]"
typed_time = b"%(DIGIT)s+%(fixed_len_time_unit)s?" % bglobals()

username = non_ws_string
sessionid = number
sessionversion = number
nettype = NetTypes.REPattern()
addrtype = AddrTypes.REPattern()
address = non_ws_string
start_time = time_or_zero
stop_time = time_or_zero
port = b"\d+"
repeat_interval = b"[1-9]%(DIGIT)s*%(fixed_len_time_unit)s?" % bglobals()
media = MediaTypes.REPattern()
trans_proto = b"%(token)s(?:/%(token)s)*" % bglobals()
fmt = token
media_field = (
    b"%(LineTypes.m)s=%(media)s%(SP)s%(port)s(?:/%(integer)s)?%(SP)s"
    b"%(trans_proto)s(?:%(SP)s%(fmt)s)%(eol)s" % bglobals())

repeat_fields = (
    b"%(LineTypes.m)s=%(repeat_interval)s(?:%(SP)s%(typed_time)s){2,}"
    b"" % bglobals()
)
zone_adjustments = (
    b"%(LineTypes.z)s=%(time)s%(SP)s-?%(typed_time)s"
    b"(?:%(SP)s%(time)s%(SP)s-?%(typed_time)s)*" % bglobals()
)
time_fields = (
    b"(?:"
    b"%(LineTypes.t)s=%(start_time)s%(SP)s%(stop_time)s"
    b"(?:%(eol)s%(repeat_fields)s)*%(eol)s"
    b")+"
    b"(?:%(zone_adjustments)s%(eol)s)?"
    b"" % bglobals())

media_fields = (
    b"(?:"
    b"%(media_field)s"
    b"(?:%(LineTypes.i)s=(%(text)s)%(eol)s)?"
    b"(?:%(LineTypes.c)s=%(text)s%(eol)s)?"
    b"(?:%(LineTypes.b)s=%(text)s%(eol)s)*"
    b"(?:%(LineTypes.k)s=%(text)s%(eol)s)?"
    b"(?:%(LineTypes.a)s=%(text)s%(eol)s)*"
    b")*" % bglobals())

MediaProtocols = AsciiBytesEnum(
    (b"RTP/AVP", ), normalize=lambda x: x.replace(b'_', b'/'))

SIPBodyType = b"application/sdp"

#
# =================== Pre-compiled REs ========================================
#
username_only_re = re.compile(b"%(username)s$" % bglobals())
fmt_space_re = re.compile(b"%(space)s" % bglobals())


#
# =================== Conversions and Checks ==================================
#
def AddressToSDPAddrType(address):
    if address is None:
        return None
    try:
        if IPv6address_only_re.match(address):
            return AddrTypes.IP6

        if IPv4address_only_re.match(address):
            return AddrTypes.IP4
    except TypeError as exc:
        exc.args += ('type of address: %r' % address.__class__.__name__,)
        raise

    # address not obviously IP4 or IP6 so raise
    raise ValueError(
        "Address %r is not an IPv4 or IPv6 address" % (address,))


def sdp_username_is_ok(uname):
    if isinstance(uname, str):
        uname = abytes(uname)
    return username_only_re.match(uname) is not None


def sock_family_to_addr_type(sock_family):

    if sock_family is None:
        return None

    if sock_family == AF_INET:
        return AddrTypes.IP4

    if sock_family == AF_INET6:
        return AddrTypes.IP6

    raise ValueError('Unknown socket family: %r' % sock_family)

bdict = bglobals()
