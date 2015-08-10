"""prot.py

This module contains details on the SIP protocol from RFC3261, and should
generally not require any of the other sip specific code.

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
from sipparty.util import Enum

# Refer to https://tools.ietf.org/html/rfc3261#section-25.1 for the ABNF.
CRLF = b"\r\n"
SP = b" "
HTAB = b"\t"
WS = b"[ \t]".format(**locals())
LWS = b"(?:{WS}*{CRLF})?{WS}+".format(**locals())  # Linear whitespace.
SWS = b"(?:{LWS})?".format(**locals())  # Separator whitespace.
HCOLON = b"{WS}*:{SWS}".format(**locals())
SEMI = b"{SWS};{SWS}".format(**locals())
SLASH = b"{SWS}/{SWS}".format(**locals())
COLON = b"{SWS}:{SWS}".format(**locals())
upper_alpharange = b"A-Z"
upper_alpha = b"[{upper_alpharange}]".format(**locals())
alpharange = b"a-z{upper_alpharange}".format(**locals())
ALPHA = b"[{alpharange}]".format(**locals())
digitrange = b"0-9"
DIGIT = b"[{digitrange}]".format(**locals())
hexrange = b"{digitrange}a-fA-F".format(**locals())
HEXDIG = b"[{hexrange}]".format(**locals())
EQUAL = b"{SWS}={SWS}".format(**locals())
DQUOTE = b"\""
LAQUOT = b"<"
RAQUOT = b">"
CHARrange = b"\x01-\x7F"  # As per RFC 2326.
CHAR = b"[{CHARrange}]".format(**locals())
UTF8_CONT = b"[\x80-\xbf]"
UTF8_NONASCIIopts = (
    b"[\xc0-\xdf]{UTF8_CONT}|"
    "[\xe0-\xef]{UTF8_CONT}{{2}}|"
    "[\xf0-\xf7]{UTF8_CONT}{{3}}|"
    "[\xf8-\xfb]{UTF8_CONT}{{4}}|"
    "[\xfc-\xfd]{UTF8_CONT}{{5}}"
    "".format(**locals()))
UTF8_NONASCII = b"(?:{UTF8_NONASCIIopts})".format(**locals())
TEXT_UTF8charopts = (
    b"[\x21-\x7e]|{UTF8_NONASCIIopts}"
    "".format(**locals()))
TEXT_UTF8char = b"(?:{TEXT_UTF8charopts})".format(**locals())
TEXT_UTF8charsopts = (
    b"[\x21-\x7e]+|{UTF8_NONASCIIopts}"
    "".format(**locals()))
TEXT_UTF8chars = b"(?:{TEXT_UTF8charopts})".format(**locals())
alphanumrange = b"{alpharange}{digitrange}".format(**locals())
alphanum = b"[{alphanumrange}]".format(**locals())
markrange = b"_.!~*'()-"
mark = b"[{markrange}]".format(**locals())
unreservedrange = b"{alphanumrange}{markrange}".format(**locals())
unreserved = b"[{unreservedrange}]".format(**locals())
reservedrange = b";/?:@&=+$,"
reserved = b"[{reservedrange}]".format(**locals())
escaped = b"%{HEXDIG}{HEXDIG}".format(**locals())
user_unreservedrange = b"&=+$,;?/"
user_unreserved = b"[{user_unreservedrange}]".format(**locals())

# The following come from RFC 2806.
token_charrange = (
    b"!\x23-\x27*\x2b-\x2d{alphanumrange}^_`|~".format(**locals()))
token_char = b"[{token_charrange}]".format(**locals())
quoted_string = (
    b"\"(?:[\x20-\x21\x23-\x7E\x80-\xFF]+|\\{CHAR})*\"".format(**locals()))
visual_separatorrange = b".()-"
visual_separator = b"[{visual_separatorrange}]".format(**locals())
phonedigitrange = b"{digitrange}{visual_separatorrange}".format(**locals())
phonedigit = b"[{phonedigitrange}]".format(**locals())
dtmf_digitrange = b"*#ABCD"
dtmf_digit = b"[{dtmf_digitrange}]".format(**locals())
one_second_pause = b"p"
wait_for_dial_tone = b"w"
pause_characterrange = (
    b"{one_second_pause}{wait_for_dial_tone}".format(**locals()))
pause_character = b"[{pause_characterrange}]".format(**locals())
base_phone_number = b"{phonedigit}+".format(**locals())
# The following are special cases of extensions that aren't needed yet.
# isdn-subaddress       = ";isub=" 1*phonedigit
# post-dial             = ";postd=" 1*(phonedigit /
#                         dtmf-digit / pause-character)
# area-specifier        = ";" phone-context-tag "=" phone-context-ident
# service_provider      = provider-tag "=" provider-hostname
future_extension = (
    b";{token_char}+"
    "(?:=(?:{token_char}+(?:[?]{token_char}+)|{quoted_string}))?"
    "".format(**locals()))
global_phone_number = (
    b"[+]{base_phone_number}(?:{future_extension})*"
    "".format(**locals()))
local_phone_number = (
    b"[{dtmf_digitrange}{pause_characterrange}{phonedigitrange}]+"
    "(?:{future_extension})*"
    "".format(**locals()))
telephone_subscriber = (
    b"(?:{global_phone_number}|{local_phone_number})".format(**locals()))

token = b"[{alphanumrange}\x23-\x5F.!%*+`'~]+".format(**locals())
STAR = b"*"

# The end of line string used in SIP messages.
EOL = CRLF

# Magic cookie used in branch parameters.
BranchMagicCookie = b"z9hG4bK"

hex4 = b"{HEXDIG}{{1,4}}".format(**locals())
# Surely IPv6 address length is limited?
hexseq = b"{hex4}(?::{hex4})*".format(**locals())
hexpart = b"(?:{hexseq}|{hexseq}::(?:{hexseq})?|::(?:{hexseq})?)".format(
    **locals())
IPv4address = b"{DIGIT}{{1,3}}(?:[.]{DIGIT}{{1,3}}){{3}}".format(**locals())
IPv6address = b"{hexpart}(?::{IPv4address})?".format(**locals())
IPv6reference = b"[[]{IPv6address}[]]".format(**locals())
port = b"{DIGIT}+".format(**locals())
toplabel = b"{ALPHA}(?:[{alphanumrange}-]*{alphanum})?".format(
    **locals())
domainlabel = b"(?:{alphanum}|{alphanum}[{alphanumrange}-]*{alphanum})".format(
    **locals())
hostname = b"(?:{domainlabel}[.])*{toplabel}[.]?".format(**locals())
host = b"(?:{hostname}|{IPv4address}|{IPv6reference})".format(**locals())
hostport = b"{host}(?::{port})?".format(**locals())
# Should be SIP or token, but just use token.
protocol_name = token
protocol_version = token
sent_protocol = b"{protocol_name}{SLASH}{protocol_version}".format(**locals())
# TODO qdtext should include UTF8-NONASCII.
qdtext = b"(?:{LWS}|[\x21\x23-\x5B\x5D-\x7E])".format(**locals())
quoted_pair = b"\\[\x00-\x09\x0B-\x0C\x0E-\x7F]"
quoted_string = b"{SWS}{DQUOTE}(?:{qdtext}|{quoted_pair})*{DQUOTE}".format(
    **locals())
gen_value = b"(?:{token}|{host}|{quoted_string})".format(**locals())
generic_param = b"{token}(?:{EQUAL}{gen_value})?".format(**locals())
sent_by = b"{host}(?:{COLON}{port})?".format(**locals())
via_parm = b"{sent_protocol}{LWS}{sent_by}".format(**locals())
# transport actually includes specific sets of token as well in the spec.
transport = token

user = (
    b"(?:[{user_unreservedrange}{unreservedrange}]+|{escaped})+"
    "".format(**locals()))
password = (
    b"(?:[&=+$,{unreservedrange}]+|{escaped})*"
    "".format(**locals()))
userinfo = (
    b"(?:{user}|{telephone_subscriber})(?::{password})?@".format(**locals()))
scheme = b"{ALPHA}[{alphanumrange}\x2b-\x2e]*".format(**locals())
srvr = b"(?:(?:{userinfo}@)?{hostport})?".format(**locals())
reg_name = b"(?:[$,;:@&=+{unreservedrange}]|{escaped})+".format(**locals())
authority = b"(?:{srvr}|{reg_name})".format(**locals())
pchar = b"(?:[:@&=+$,{unreservedrange}]|{escaped})".format(**locals())
param = b"(?:{pchar})*".format(**locals())
segment = b"{pchar}(?:;{param})*".format(**locals())
path_segments = b"{segment}(?:/{segment})*".format(**locals())
abs_path = b"/{path_segments}".format(**locals())
net_path = b"//{authority}(?:{abs_path})?".format(**locals())
uric = b"(?:[{reservedrange}{unreservedrange}]+|{escaped})".format(**locals())
uric_no_slash = (
    b"(?:[;?:@&=+$,{unreservedrange}]+|{escaped})".format(**locals()))
query = b"{uric}*".format(**locals())
hier_part = b"(?:{net_path}|{abs_path})(?:[?]{query})?".format(**locals())
opaque_part = b"{uric_no_slash}{uric}*".format(**locals())
absoluteURI = b"{scheme}:(?:{hier_part}|{opaque_part})".format(**locals())
display_name = b"(?:(?:{token}{LWS})*|{quoted_string})".format(**locals())
param_unreservedrange = b"][/:&+$"
param_unreserved = b"[{param_unreservedrange}]".format(**locals())
# paramchars is paramchar but with an optimization to match several characters
# in a row.
paramchars = (
    b"(?:[{param_unreservedrange}{unreservedrange}]+|{escaped})+"
    "".format(**locals()))
uri_parameter = b"{paramchars}(?:={paramchars})?".format(**locals())
uri_parameters = b"(?:;{uri_parameter})*".format(**locals())
hnv_unreservedrange = b"][/?:+$"
hnv_unreserved = b"[{hnv_unreservedrange}]".format(**locals())
hname = (
    b"(?:[{hnv_unreservedrange}{unreservedrange}]+|{escaped})+"
    "".format(**locals()))
hvalue = (
    b"(?:[{hnv_unreservedrange}{unreservedrange}]+|{escaped})*"
    "".format(**locals()))
header = b"{hname}={hvalue}".format(**locals())
headers = b"[?]{header}(?:[&]{header})*".format(**locals())
sip_sips_body = (
    b"(?:{userinfo})?{hostport}{uri_parameters}(?:{headers})?"
    "".format(**locals()))
SIP_URI = b"sip:{sip_sips_body}".format(**locals())
SIPS_URI = b"sips:{sip_sips_body}".format(**locals())
addr_spec = b"(?:{SIP_URI}|{SIPS_URI}|{absoluteURI})".format(**locals())
name_addr = (
    b"(?:{display_name})?{LAQUOT}{addr_spec}{RAQUOT}".format(**locals()))

Method = b"[{upper_alpharange}]+".format(**locals())
Request_URI = b"(?:sips?{sip_sips_body}|{absoluteURI})".format(**locals())
SIP_Version = b"SIP/{DIGIT}+[.]{DIGIT}+".format(**locals())

Status_Code = b"{DIGIT}{{3}}".format(**locals())
# Reason phrase should be a bit more complicated:
# Reason-Phrase   =  *(reserved / unreserved / escaped
#                    / UTF8-NONASCII / UTF8-CONT / SP / HTAB)
Reason_Phrase = (
    b"(?:[{reservedrange}{SP}{HTAB}{unreservedrange}]+|"
    "{escaped})*".format(**locals()))

header_name = token
header_value = (
    b"(?:{TEXT_UTF8charsopts}|{LWS}|{UTF8_CONT})*".format(**locals()))
extension_header = b"{header_name}{HCOLON}{header_value}".format(**locals())

RequestTypes = Enum((
    "ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"),
    normalize=lambda x: bytes(x).upper())

ResponseCodeMessages = {
    1: b"Unknown Trying Response",
    2: b"Unknown Successful Response",
    200: b"OK",
    202: b"Accepted",
    204: b"No Notification",
    3: b"Unknown redirect response",
    300: b"Multiple Choices",
    301: b"Moved Permanently",
    302: b"Moved Temporarily",
    305: b"Use Proxy",
    380: b"Alternative Service",
    4: b"Unknown Client Error Response",
    400: b"Bad Request",
    401: b"Unauthorized",
    402: b"Payment Required",
    403: b"Forbidden",
    404: b"Not Found",
    405: b"Method Not Allowed",
    406: b"Not Acceptable",
    407: b"Proxy Authentication Required",
    408: b"Request Timeout",
    409: b"Conflict",
    410: b"Gone",
    411: b"Length Required",
    412: b"Conditional Request Failed",
    413: b"Request Entity Too Large",
    414: b"Request-URI Too Long",
    415: b"Unsupported Media Type",
    416: b"Unsupported URI Scheme",
    417: b"Unknown Resource-Priority",
    420: b"Bad Extension",
    421: b"Extension Required",
    422: b"Session Interval Too Small",
    423: b"Interval Too Brief",
    424: b"Bad Location Information",
    428: b"Use Identity Header",
    429: b"Provide Referrer Identity",
    430: b"Flow Failed",
    433: b"Anonymity Disallowed",
    436: b"Bad Identity-Info",
    437: b"Unsupported Certificate",
    438: b"Invalid Identity Header",
    439: b"First Hop Lacks Outbound Support",
    470: b"Consent Needed",
    480: b"Temporarily Unavailable",
    481: b"Call/Transaction Does Not Exist",
    482: b"Loop Detected.",
    483: b"Too Many Hops",
    484: b"Address Incomplete",
    485: b"Ambiguous",
    486: b"Busy Here",
    487: b"Request Terminated",
    488: b"Not Acceptable Here",
    489: b"Bad Event",
    491: b"Request Pending",
    493: b"Undecipherable",
    494: b"Security Agreement Required",
    5: b"Unknown Server Error Response",
    500: b"Server Internal Error",
    501: b"Not Implemented",
    502: b"Bad Gateway",
    503: b"Service Unavailable",
    504: b"Server Time-out",
    505: b"Version Not Supported",
    513: b"Message Too Large",
    580: b"Precondition Failure",
    6: b"Unknown Global Failure Response",
    600: b"Busy Everywhere",
    603: b"Decline",
    604: b"Does Not Exist Anywhere",
    606: b"Not Acceptable",
}


class ProtocolError(Exception):
    """Something didn't make sense in SIP."""
    pass


class ProtocolSyntaxError(ProtocolError):
    """Syntax errors are when a request is missing some key bit from the
    protocol, or is otherwise confused. Like trying to build
    a request with a response code.
    """


class Incomplete(ProtocolError):
    """Could not make a SIP message because it was incomplete.
    """


def ProvisionalDialogID(CallIDText, localTagText):
    return (CallIDText, localTagText)


def EstablishedDialogID(CallIDText, localTagText, remoteTagText):
    return (CallIDText, localTagText, remoteTagText)


def ProvisionalDialogIDFromEstablishedID(estDID):
    return estDID[:2]
