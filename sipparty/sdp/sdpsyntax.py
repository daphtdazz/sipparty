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
from sipparty import util
from sipparty.transport import (IPv4address_re, IPv6address_re)

NetTypes = util.Enum((b"IN",))
AddrTypes = util.Enum((b"IP4", b"IP6"))
MediaTypes = util.Enum(
    (b"audio", b"video", b"text", b"application", b"message"))
LineTypes = util.Enum(
    aliases={
        "version": b"v",
        "origin": b"o",
        "sessionname": b"s",
        "info": b"i",
        "uri": b"u",
        "email": b"e",
        "phone": b"p",
        "connectioninfo": b"c",
        "bandwidthinfo": b"b",
        "time": b"t",
        "repeat": b"r",
        "timezone": b"z",
        "encryptionkey": b"k",
        "attribute": b"a",
        "media": b"m"
    })

DIGIT = b"\d"
number = b"{DIGIT}+".format(**locals())
SP = b"\x20"
space = SP
VCHAR = b"\x21-\x7e"
eol = b"\r?\n"
token_char = b"[\x21\x23-\x27\x2a\x2b\x2d\x2e\x30-\x39\x41-\x5a\x5e-\x7e]"
token = b"{token_char}+".format(**locals())

supportedversions = b"0"

non_ws_string = b"[{VCHAR}\x80-\xff]+".format(**locals())
text = b"[^\x00\x0a\x0d]+"
integer = b"[1-9]\d*"
time = b"[1-9][0-9]{9,}"
time_or_zero = b"(?:0|{time})".format(**locals())
fixed_len_time_unit = b"[dhms]"
typed_time = b"{DIGIT}+{fixed_len_time_unit}?".format(**locals())

username = non_ws_string
sessionid = number
sessionversion = number
nettype = NetTypes.REPattern()
addrtype = AddrTypes.REPattern()
address = non_ws_string
start_time = time_or_zero
stop_time = time_or_zero
port = b"\d+"
repeat_interval = b"[1-9]{DIGIT}*{fixed_len_time_unit}?".format(**locals())
media = MediaTypes.REPattern()
trans_proto = b"{token}(?:/{token})*".format(**locals())
fmt = token
media_field = (
    b"{LineTypes.media}={media}{SP}{port}(?:/{integer})?{SP}{trans_proto}"
    "(?:{SP}{fmt}){eol}"
    "".format(**locals()))

repeat_fields = (
    b"{LineTypes.repeat}={repeat_interval}(?:{SP}{typed_time}){{2,}}"
    "".format(**locals())
)
zone_adjustments = (
    b"{LineTypes.timezone}={time}{SP}-?{typed_time}"
    "(?:{SP}{time}{SP}-?{typed_time})*".format(**locals())
)
time_fields = (
    b"(?:"
    "{LineTypes.time}={start_time}{SP}{stop_time}"
    "(?:{eol}{repeat_fields})*{eol}"
    ")+"
    "(?:{zone_adjustments}{eol})?"
    "".format(**locals()))

media_fields = (
    b"(?:"
    "{media_field}"
    "(?:{LineTypes.info}=({text}){eol})?"
    "(?:{LineTypes.connectioninfo}={text}{eol})?"
    "(?:{LineTypes.bandwidthinfo}={text}{eol})*"
    "(?:{LineTypes.encryptionkey}={text}{eol})?"
    "(?:{LineTypes.attribute}={text}{eol})*"
    ")*".format(**locals()))

MediaProtocols = util.Enum(
    (b"RTP/AVP", ), normalize=lambda x: x.replace(b'_', b'/'))

SIPBodyType = b"application/sdp"

#
# =================== Pre-compiled REs ========================================
#
username_re = re.compile("{username}$".format(**locals()))
fmt_space_re = re.compile("{space}".format(**locals()))


#
# =================== Conversions =======================================
#
def AddressToSDPAddrType(address):

    if IPv6address_re.match(address):
        return AddrTypes.IP6

    if IPv4address_re.match(address):
        return AddrTypes.IP4

    # address not obviously IP4 or IP6 so return None
    raise ValueError(
        "Address %r is not an IPv4 or IPv6 address" % (address,))
