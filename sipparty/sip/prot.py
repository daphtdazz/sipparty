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
from sipparty.transport import (
    digitrange, DIGIT, hexrange, HEXDIG, hex4, hexseq, hexpart, IPv4address,
    IPv6address, port)

protocols = Enum(("SIP/2.0",), normalize=lambda p: p.upper())

# Refer to https://tools.ietf.org/html/rfc3261#section-25.1 for the ABNF.
CRLF = "\r\n"
SP = " "
HTAB = "\t"
WS = "[ \t]".format(**locals())
LWS = "(?:{WS}*{CRLF})?{WS}+".format(**locals())  # Linear whitespace.
SWS = "(?:{LWS})?".format(**locals())  # Separator whitespace.
HCOLON = "{WS}*:{SWS}".format(**locals())
SEMI = "{SWS};{SWS}".format(**locals())
SLASH = "{SWS}/{SWS}".format(**locals())
COLON = "{SWS}:{SWS}".format(**locals())
upper_alpharange = "A-Z"
upper_alpha = "[{upper_alpharange}]".format(**locals())
alpharange = "a-z{upper_alpharange}".format(**locals())
ALPHA = "[{alpharange}]".format(**locals())
EQUAL = "{SWS}={SWS}".format(**locals())
DQUOTE = "\""
LAQUOT = "<"
RAQUOT = ">"
CHARrange = "\x01-\x7F"  # As per RFC 2326.
CHAR = "[{CHARrange}]".format(**locals())
UTF8_CONT = "[\x80-\xbf]"
UTF8_NONASCIIopts = (
    "[\xc0-\xdf]{UTF8_CONT}|"
    "[\xe0-\xef]{UTF8_CONT}{{2}}|"
    "[\xf0-\xf7]{UTF8_CONT}{{3}}|"
    "[\xf8-\xfb]{UTF8_CONT}{{4}}|"
    "[\xfc-\xfd]{UTF8_CONT}{{5}}"
    "".format(**locals()))
UTF8_NONASCII = "(?:{UTF8_NONASCIIopts})".format(**locals())
TEXT_UTF8charopts = (
    "[\x21-\x7e]|{UTF8_NONASCIIopts}"
    "".format(**locals()))
TEXT_UTF8char = "(?:{TEXT_UTF8charopts})".format(**locals())
TEXT_UTF8charsopts = (
    "[\x21-\x7e]+|{UTF8_NONASCIIopts}"
    "".format(**locals()))
TEXT_UTF8chars = "(?:{TEXT_UTF8charopts})".format(**locals())
alphanumrange = "{alpharange}{digitrange}".format(**locals())
alphanum = "[{alphanumrange}]".format(**locals())
markrange = "_.!~*'()-"
mark = "[{markrange}]".format(**locals())
unreservedrange = "{alphanumrange}{markrange}".format(**locals())
unreserved = "[{unreservedrange}]".format(**locals())
reservedrange = ";/?:@&=+$,"
reserved = "[{reservedrange}]".format(**locals())
escaped = "%{HEXDIG}{HEXDIG}".format(**locals())
user_unreservedrange = "&=+$,;?/"
user_unreserved = "[{user_unreservedrange}]".format(**locals())

# The following come from RFC 2806.
token_charrange = (
    "!\x23-\x27*\x2b-\x2d{alphanumrange}^_`|~".format(**locals()))
token_char = "[{token_charrange}]".format(**locals())
quoted_string = (
    "\"(?:[\x20-\x21\x23-\x7E\x80-\xFF]+|\\{CHAR})*\"".format(**locals()))
visual_separatorrange = ".()-"
visual_separator = "[{visual_separatorrange}]".format(**locals())
phonedigitrange = "{digitrange}{visual_separatorrange}".format(**locals())
phonedigit = "[{phonedigitrange}]".format(**locals())
dtmf_digitrange = "*#ABCD"
dtmf_digit = "[{dtmf_digitrange}]".format(**locals())
one_second_pause = "p"
wait_for_dial_tone = "w"
pause_characterrange = (
    "{one_second_pause}{wait_for_dial_tone}".format(**locals()))
pause_character = "[{pause_characterrange}]".format(**locals())
base_phone_number = "{phonedigit}+".format(**locals())
# The following are special cases of extensions that aren't needed yet.
# isdn-subaddress       = ";isub=" 1*phonedigit
# post-dial             = ";postd=" 1*(phonedigit /
#                         dtmf-digit / pause-character)
# area-specifier        = ";" phone-context-tag "=" phone-context-ident
# service_provider      = provider-tag "=" provider-hostname
future_extension = (
    ";{token_char}+"
    "(?:=(?:{token_char}+(?:[?]{token_char}+)|{quoted_string}))?"
    "".format(**locals()))
global_phone_number = (
    "[+]{base_phone_number}(?:{future_extension})*"
    "".format(**locals()))
local_phone_number = (
    "[{dtmf_digitrange}{pause_characterrange}{phonedigitrange}]+"
    "(?:{future_extension})*"
    "".format(**locals()))
telephone_subscriber = (
    "(?:{global_phone_number}|{local_phone_number})".format(**locals()))

token = "[{alphanumrange}\x23-\x5F.!%*+`'~]+".format(**locals())
STAR = "[*]"

# The end of line string used in SIP messages.
EOL = CRLF

# Magic cookie used in branch parameters.
BranchMagicCookie = "z9hG4bK"


toplabel = "{ALPHA}(?:[{alphanumrange}-]*{alphanum})?".format(
    **locals())
domainlabel = "(?:{alphanum}|{alphanum}[{alphanumrange}-]*{alphanum})".format(
    **locals())
hostname = "(?:{domainlabel}[.])*{toplabel}[.]?".format(**locals())
IPv6reference = "[[]{IPv6address}[]]".format(**locals())
host = "(?:{hostname}|{IPv4address}|{IPv6reference})".format(**locals())
hostport = "{host}(?::{port})?".format(**locals())
# Should be SIP or token, but just use token.
protocol_name = token
protocol_version = token
sent_protocol = "{protocol_name}{SLASH}{protocol_version}".format(**locals())
# TODO qdtext should include UTF8-NONASCII.
qdtext = "(?:{LWS}|[\x21\x23-\x5B\x5D-\x7E])".format(**locals())
quoted_pair = "\\[\x00-\x09\x0B-\x0C\x0E-\x7F]"
quoted_string = "{SWS}{DQUOTE}(?:{qdtext}|{quoted_pair})*{DQUOTE}".format(
    **locals())
gen_value = "(?:{token}|{host}|{quoted_string})".format(**locals())
generic_param = "{token}(?:{EQUAL}{gen_value})?".format(**locals())
sent_by = "{host}(?:{COLON}{port})?".format(**locals())
via_parm = "{sent_protocol}{LWS}{sent_by}".format(**locals())
# transport actually includes specific sets of token as well in the spec.
transport = token

user = (
    "(?:[{user_unreservedrange}{unreservedrange}]+|{escaped})+"
    "".format(**locals()))
password = (
    "(?:[&=+$,{unreservedrange}]+|{escaped})*"
    "".format(**locals()))
userinfo = (
    "(?:{user}|{telephone_subscriber})(?::{password})?@".format(**locals()))
scheme = "{ALPHA}[{alphanumrange}\x2b-\x2e]*".format(**locals())
srvr = "(?:(?:{userinfo}@)?{hostport})?".format(**locals())
reg_name = "(?:[$,;:@&=+{unreservedrange}]|{escaped})+".format(**locals())
authority = "(?:{srvr}|{reg_name})".format(**locals())
pchar = "(?:[:@&=+$,{unreservedrange}]|{escaped})".format(**locals())
param = "(?:{pchar})*".format(**locals())
segment = "{pchar}(?:;{param})*".format(**locals())
path_segments = "{segment}(?:/{segment})*".format(**locals())
abs_path = "/{path_segments}".format(**locals())
net_path = "//{authority}(?:{abs_path})?".format(**locals())
uric = "(?:[{reservedrange}{unreservedrange}]+|{escaped})".format(**locals())
uric_no_slash = (
    "(?:[;?:@&=+$,{unreservedrange}]+|{escaped})".format(**locals()))
query = "{uric}*".format(**locals())
hier_part = "(?:{net_path}|{abs_path})(?:[?]{query})?".format(**locals())
opaque_part = "{uric_no_slash}{uric}*".format(**locals())
absoluteURI = "{scheme}:(?:{hier_part}|{opaque_part})".format(**locals())
display_name = "(?:(?:{token}{LWS})*|{quoted_string})".format(**locals())
param_unreservedrange = "][/:&+$"
param_unreserved = "[{param_unreservedrange}]".format(**locals())
# paramchars is paramchar but with an optimization to match several characters
# in a row.
paramchars = (
    "(?:[{param_unreservedrange}{unreservedrange}]+|{escaped})+"
    "".format(**locals()))
uri_parameter = "{paramchars}(?:={paramchars})?".format(**locals())
uri_parameters = "(?:;{uri_parameter})*".format(**locals())
hnv_unreservedrange = "][/?:+$"
hnv_unreserved = "[{hnv_unreservedrange}]".format(**locals())
hname = (
    "(?:[{hnv_unreservedrange}{unreservedrange}]+|{escaped})+"
    "".format(**locals()))
hvalue = (
    "(?:[{hnv_unreservedrange}{unreservedrange}]+|{escaped})*"
    "".format(**locals()))
header = "{hname}={hvalue}".format(**locals())
headers = "[?]{header}(?:[&]{header})*".format(**locals())
sip_sips_body = (
    "(?:{userinfo})?{hostport}{uri_parameters}(?:{headers})?"
    "".format(**locals()))
SIP_URI = "sip:{sip_sips_body}".format(**locals())
SIPS_URI = "sips:{sip_sips_body}".format(**locals())
addr_spec = "(?:{SIP_URI}|{SIPS_URI}|{absoluteURI})".format(**locals())
name_addr = (
    "(?:{display_name})?{LAQUOT}{addr_spec}{RAQUOT}".format(**locals()))

Method = "[{upper_alpharange}]+".format(**locals())
Request_URI = "(?:sips?{sip_sips_body}|{absoluteURI})".format(**locals())
SIP_Version = "SIP/{DIGIT}+[.]{DIGIT}+".format(**locals())

Status_Code = "{DIGIT}{{3}}".format(**locals())
# Reason phrase should be a bit more complicated:
# Reason-Phrase   =  *(reserved / unreserved / escaped
#                    / UTF8-NONASCII / UTF8-CONT / SP / HTAB)
Reason_Phrase = (
    "(?:[{reservedrange}{SP}{HTAB}{unreservedrange}]+|"
    "{escaped})*".format(**locals()))

header_name = token
header_value = (
    "(?:{TEXT_UTF8charsopts}|{LWS}|{UTF8_CONT})*".format(**locals()))
extension_header = "{header_name}{HCOLON}{header_value}".format(**locals())

# Message types. There are specific types defined but token represents them
# all.
m_type = "{token}".format(**locals())
m_subtype = "{token}".format(**locals())
m_parameter = "{token}=(?:{quoted_string}|{token})".format(**locals())

RequestTypes = Enum((
    "ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"),
    normalize=lambda x: bytes(x).upper())

ResponseCodeMessages = {
    1: "Unknown Trying Response",
    2: "Unknown Successful Response",
    200: "OK",
    202: "Accepted",
    204: "No Notification",
    3: "Unknown redirect response",
    300: "Multiple Choices",
    301: "Moved Permanently",
    302: "Moved Temporarily",
    305: "Use Proxy",
    380: "Alternative Service",
    4: "Unknown Client Error Response",
    400: "Bad Request",
    401: "Unauthorized",
    402: "Payment Required",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    411: "Length Required",
    412: "Conditional Request Failed",
    413: "Request Entity Too Large",
    414: "Request-URI Too Long",
    415: "Unsupported Media Type",
    416: "Unsupported URI Scheme",
    417: "Unknown Resource-Priority",
    420: "Bad Extension",
    421: "Extension Required",
    422: "Session Interval Too Small",
    423: "Interval Too Brief",
    424: "Bad Location Information",
    428: "Use Identity Header",
    429: "Provide Referrer Identity",
    430: "Flow Failed",
    433: "Anonymity Disallowed",
    436: "Bad Identity-Info",
    437: "Unsupported Certificate",
    438: "Invalid Identity Header",
    439: "First Hop Lacks Outbound Support",
    470: "Consent Needed",
    480: "Temporarily Unavailable",
    481: "Call/Transaction Does Not Exist",
    482: "Loop Detected.",
    483: "Too Many Hops",
    484: "Address Incomplete",
    485: "Ambiguous",
    486: "Busy Here",
    487: "Request Terminated",
    488: "Not Acceptable Here",
    489: "Bad Event",
    491: "Request Pending",
    493: "Undecipherable",
    494: "Security Agreement Required",
    5: "Unknown Server Error Response",
    500: "Server Internal Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Server Time-out",
    505: "Version Not Supported",
    513: "Message Too Large",
    580: "Precondition Failure",
    6: "Unknown Global Failure Response",
    600: "Busy Everywhere",
    603: "Decline",
    604: "Does Not Exist Anywhere",
    606: "Not Acceptable",
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
