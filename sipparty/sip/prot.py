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
from six import PY2
from ..transport import (
    digitrange, DIGIT, hexrange, HEXDIG, hex4, hexseq, hexpart, IPv4address,
    IPv6address, port)
from ..util import (AsciiBytesEnum, astr, bglobals_g, Enum, sipheader)


def bglobals():
    return bglobals_g(globals())


def str_enumify(bytes_enum):
    if PY2:
        return bytes_enum
    return Enum(
        [astr(rtype) for rtype in bytes_enum],
        normalize=bytes_enum._en_normalize, aliases=bytes_enum._en_aliases)

protocols = AsciiBytesEnum((b"SIP/2.0",), normalize=lambda p: p.upper())

# Refer to https://tools.ietf.org/html/rfc3261#section-25.1 for the ABNF.
CRLF = b"\r\n"
SP = b" "
HTAB = b"\t"
WS = b"[ \t]" % bglobals()
LWS = b"(?:%(WS)s*%(CRLF)s)?%(WS)s+" % bglobals()  # Linear whitespace.
SWS = b"(?:%(LWS)s)?" % bglobals()  # Separator whitespace.
HCOLON = b"%(WS)s*:%(SWS)s" % bglobals()
SEMI = b"%(SWS)s;%(SWS)s" % bglobals()
SLASH = b"%(SWS)s/%(SWS)s" % bglobals()
COLON = b"%(SWS)s:%(SWS)s" % bglobals()
upper_alpharange = b"A-Z"
upper_alpha = b"[%(upper_alpharange)s]" % bglobals()
alpharange = b"a-z%(upper_alpharange)s" % bglobals()
ALPHA = b"[%(alpharange)s]" % bglobals()
EQUAL = b"%(SWS)s=%(SWS)s" % bglobals()
DQUOTE = b"\""
LAQUOT = b"<"
RAQUOT = b">"
CHARrange = b"\x01-\x7F"  # As per RFC 2326.
CHAR = b"[%(CHARrange)s]" % bglobals()
UTF8_CONT = b"[\x80-\xbf]"
UTF8_NONASCIIopts = (
    b"[\xc0-\xdf]%(UTF8_CONT)s|"
    b"[\xe0-\xef]%(UTF8_CONT)s{2}|"
    b"[\xf0-\xf7]%(UTF8_CONT)s{3}|"
    b"[\xf8-\xfb]%(UTF8_CONT)s{4}|"
    b"[\xfc-\xfd]%(UTF8_CONT)s{5}"
    b"" % bglobals())
UTF8_NONASCII = b"(?:%(UTF8_NONASCIIopts)s)" % bglobals()
TEXT_UTF8charopts = (
    b"[\x21-\x7e]|%(UTF8_NONASCIIopts)s"
    b"" % bglobals())
TEXT_UTF8char = b"(?:%(TEXT_UTF8charopts)s)" % bglobals()
TEXT_UTF8charsopts = (
    b"[\x21-\x7e]+|%(UTF8_NONASCIIopts)s"
    b"" % bglobals())
TEXT_UTF8chars = b"(?:%(TEXT_UTF8charopts)s)" % bglobals()
alphanumrange = b"%(alpharange)s%(digitrange)s" % bglobals()
alphanum = b"[%(alphanumrange)s]" % bglobals()
markrange = b"_.!~*'()-"
mark = b"[%(markrange)s]" % bglobals()
unreservedrange = b"%(alphanumrange)s%(markrange)s" % bglobals()
unreserved = b"[%(unreservedrange)s]" % bglobals()
reservedrange = b";/?:@&=+$,"
reserved = b"[%(reservedrange)s]" % bglobals()
escaped = b"%%%(HEXDIG)s%(HEXDIG)s" % bglobals()
user_unreservedrange = b"&=+$,;?/"
user_unreserved = b"[%(user_unreservedrange)s]" % bglobals()

# The following come from RFC 2806.
token_charrange = (
    b"!\x23-\x27*\x2b-\x2d%(alphanumrange)s^_`|~" % bglobals())
token_char = b"[%(token_charrange)s]" % bglobals()
quoted_string = (
    b"\"(?:[\x20-\x21\x23-\x7E\x80-\xFF]+|\\%(CHAR)s)*\"" % bglobals())
visual_separatorrange = b".()-"
visual_separator = b"[%(visual_separatorrange)s]" % bglobals()
phonedigitrange = b"%(digitrange)s%(visual_separatorrange)s" % bglobals()
phonedigit = b"[%(phonedigitrange)s]" % bglobals()
dtmf_digitrange = b"*#ABCD"
dtmf_digit = b"[%(dtmf_digitrange)s]" % bglobals()
one_second_pause = b"p"
wait_for_dial_tone = b"w"
pause_characterrange = (
    b"%(one_second_pause)s%(wait_for_dial_tone)s" % bglobals())
pause_character = b"[%(pause_characterrange)s]" % bglobals()
base_phone_number = b"%(phonedigit)s+" % bglobals()
# The following are special cases of extensions that aren't needed yet.
# isdn-subaddress       = b";isub=" 1*phonedigit
# post-dial             = b";postd=" 1*(phonedigit /
#                         dtmf-digit / pause-character)
# area-specifier        = b";" phone-context-tag b"=" phone-context-ident
# service_provider      = provider-tag "=" provider-hostname
future_extension = (
    b";%(token_char)s+"
    b"(?:=(?:%(token_char)s+(?:[?]%(token_char)s+)|%(quoted_string)s))?"
    b"" % bglobals())
global_phone_number = (
    b"[+]%(base_phone_number)s(?:%(future_extension)s)*"
    b"" % bglobals())
local_phone_number = (
    b"[%(dtmf_digitrange)s%(pause_characterrange)s%(phonedigitrange)s]+"
    b"(?:%(future_extension)s)*"
    b"" % bglobals())
telephone_subscriber = (
    b"(?:%(global_phone_number)s|%(local_phone_number)s)" % bglobals())

token = b"[%(alphanumrange)s\x23-\x5F.!%%*+`'~]+" % bglobals()
STAR = b"[*]"

# The end of line string used in SIP messages.
EOL = CRLF

# Magic cookie used in branch parameters.
BranchMagicCookie = b"z9hG4bK"


toplabel = b"%(ALPHA)s(?:[%(alphanumrange)s-]*%(alphanum)s)?" % bglobals()
domainlabel = (
    b"(?:%(alphanum)s|%(alphanum)s[%(alphanumrange)s-]*%(alphanum)s)" %
    bglobals())
hostname = b"(?:%(domainlabel)s[.])*%(toplabel)s[.]?" % bglobals()
IPv6reference = b"[[]%(IPv6address)s[]]" % bglobals()
host = b"(?:%(hostname)s|%(IPv4address)s|%(IPv6reference)s)" % bglobals()
hostport = b"%(host)s(?::%(port)s)?" % bglobals()
# Should be SIP or token, but just use token.
protocol_name = token
protocol_version = token
sent_protocol = b"%(protocol_name)s%(SLASH)s%(protocol_version)s" % bglobals()
# TODO qdtext should include UTF8-NONASCII.
qdtext = b"(?:%(LWS)s|[\x21\x23-\x5B\x5D-\x7E])" % bglobals()
quoted_pair = b"\\[\x00-\x09\x0B-\x0C\x0E-\x7F]"
quoted_string = (
    b"%(SWS)s%(DQUOTE)s(?:%(qdtext)s|%(quoted_pair)s)*%(DQUOTE)s" % bglobals())
gen_value = b"(?:%(token)s|%(host)s|%(quoted_string)s)" % bglobals()
generic_param = b"%(token)s(?:%(EQUAL)s%(gen_value)s)?" % bglobals()
sent_by = b"%(host)s(?:%(COLON)s%(port)s)?" % bglobals()
via_parm = b"%(sent_protocol)s%(LWS)s%(sent_by)s" % bglobals()
# transport actually includes specific sets of token as well in the spec.
transport = token

user = (
    b"(?:[%(user_unreservedrange)s%(unreservedrange)s]+|%(escaped)s)+"
    b"" % bglobals())
password = (
    b"(?:[&=+$,%(unreservedrange)s]+|%(escaped)s)*"
    b"" % bglobals())
userinfo = (
    b"(?:%(user)s|%(telephone_subscriber)s)(?::%(password)s)?@" % bglobals())
scheme = b"%(ALPHA)s[%(alphanumrange)s\x2b-\x2e]*" % bglobals()
srvr = b"(?:(?:%(userinfo)s@)?%(hostport)s)?" % bglobals()
reg_name = b"(?:[$,;:@&=+%(unreservedrange)s]|%(escaped)s)+" % bglobals()
authority = b"(?:%(srvr)s|%(reg_name)s)" % bglobals()
pchar = b"(?:[:@&=+$,%(unreservedrange)s]|%(escaped)s)" % bglobals()
param = b"(?:%(pchar)s)*" % bglobals()
segment = b"%(pchar)s(?:;%(param)s)*" % bglobals()
path_segments = b"%(segment)s(?:/%(segment)s)*" % bglobals()
abs_path = b"/%(path_segments)s" % bglobals()
net_path = b"//%(authority)s(?:%(abs_path)s)?" % bglobals()
uric = b"(?:[%(reservedrange)s%(unreservedrange)s]+|%(escaped)s)" % bglobals()
uric_no_slash = (
    b"(?:[;?:@&=+$,%(unreservedrange)s]+|%(escaped)s)" % bglobals())
query = b"%(uric)s*" % bglobals()
hier_part = b"(?:%(net_path)s|%(abs_path)s)(?:[?]%(query)s)?" % bglobals()
opaque_part = b"%(uric_no_slash)s%(uric)s*" % bglobals()
absoluteURI = b"%(scheme)s:(?:%(hier_part)s|%(opaque_part)s)" % bglobals()
display_name = b"(?:(?:%(token)s%(LWS)s)*|%(quoted_string)s)" % bglobals()
param_unreservedrange = b"][/:&+$"
param_unreserved = b"[%(param_unreservedrange)s]" % bglobals()
# paramchars is paramchar but with an optimization to match several characters
# in a row.
paramchars = (
    b"(?:[%(param_unreservedrange)s%(unreservedrange)s]+|%(escaped)s)+"
    b"" % bglobals())
uri_parameter = b"%(paramchars)s(?:=%(paramchars)s)?" % bglobals()
uri_parameters = b"(?:;%(uri_parameter)s)*" % bglobals()
hnv_unreservedrange = b"][/?:+$"
hnv_unreserved = b"[%(hnv_unreservedrange)s]" % bglobals()
hname = (
    b"(?:[%(hnv_unreservedrange)s%(unreservedrange)s]+|%(escaped)s)+"
    b"" % bglobals())
hvalue = (
    b"(?:[%(hnv_unreservedrange)s%(unreservedrange)s]+|%(escaped)s)*"
    b"" % bglobals())
header = b"%(hname)s=%(hvalue)s" % bglobals()
headers = b"[?]%(header)s(?:[&]%(header)s)*" % bglobals()
sip_sips_body = (
    b"(?:%(userinfo)s)?%(hostport)s%(uri_parameters)s(?:%(headers)s)?"
    b"" % bglobals())
SIP_URI = b"sip:%(sip_sips_body)s" % bglobals()
SIPS_URI = b"sips:%(sip_sips_body)s" % bglobals()
addr_spec = b"(?:%(SIP_URI)s|%(SIPS_URI)s|%(absoluteURI)s)" % bglobals()
name_addr = (
    b"(?:%(display_name)s)?%(LAQUOT)s%(addr_spec)s%(RAQUOT)s" % bglobals())

Method = b"[%(upper_alpharange)s]+" % bglobals()
Request_URI = b"(?:sips?%(sip_sips_body)s|%(absoluteURI)s)" % bglobals()
SIP_Version = b"SIP/%(DIGIT)s+[.]%(DIGIT)s+" % bglobals()

Status_Code = b"%(DIGIT)s{3}" % bglobals()
# Reason phrase should be a bit more complicated:
# Reason-Phrase   =  *(reserved / unreserved / escaped
#                    / UTF8-NONASCII / UTF8-CONT / SP / HTAB)
Reason_Phrase = (
    b"(?:[%(reservedrange)s%(SP)s%(HTAB)s%(unreservedrange)s]+|"
    b"%(escaped)s)*" % bglobals())

header_name = token
header_value = (
    b"(?:%(TEXT_UTF8charsopts)s|%(LWS)s|%(UTF8_CONT)s)*" % bglobals())
extension_header = b"%(header_name)s%(HCOLON)s%(header_value)s" % bglobals()

# Message types. There are specific types defined but token represents them
# all.
m_type = b"%(token)s" % bglobals()
m_subtype = b"%(token)s" % bglobals()
m_parameter = b"%(token)s=(?:%(quoted_string)s|%(token)s)" % bglobals()

RequestTypes = AsciiBytesEnum((
    b"ACK", b"BYE", b"CANCEL", b"INVITE", b"OPTIONS", b"REGISTER"),
    normalize=lambda x: x.upper() if hasattr(x, 'upper') else x)

RequestTypesStr = str_enumify(RequestTypes)

HeaderTypes = AsciiBytesEnum(
    (b"Accept", b"Accept-Encoding", b"Accept-Language", b"Alert-Info",
     b"Allow", b"Authentication-Info", b"Authorization", b"Call-ID",
     b"Call-Info", b"Contact", b"Content-Disposition", b"Content-Encoding",
     b"Content-Language", b"Content-Length", b"Content-Type", b"CSeq",
     b"Date", b"Error-Info", b"Expires", b"From", b"In-Reply-To",
     b"Max-Forwards", b"Min-Expires", b"MIME-Version", b"Organization",
     b"Priority", b"Proxy-Authenticate", b"Proxy-Authorization",
     b"Proxy-Require", b"Record-Route", b"Reply-To", b"Require",
     b"Retry-To", b"Route", b"Server", b"Subject", b"Supported",
     b"Timestamp", b"To", b"Unsupported", b"User-Agent", b"Via",
     b"Warning", b"WWW-Authenticate"),
    normalize=sipheader)

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

bdict = bglobals()
