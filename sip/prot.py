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

# Primitives. Refer to https://tools.ietf.org/html/rfc3261#section-25.1 for
# the ABNF.  All written out for perf reasons.
CRLF = b"\r\n"
SP = b" "
HTAB = b"\t"
WS = b"[ \t]".format(**locals())
# LWS = b"(?:{WS}*{CRLF})?{WS}+"
LWS = b"(?:{WS}*{CRLF})?{WS}+".format(**locals())  # Linear whitespace.
SWS = b"(?:{LWS})?".format(**locals())  # Separator whitespace.
HCOLON = b"{WS}*:{SWS}".format(**locals())
SEMI = b"{SWS};{SWS}".format(**locals())
SLASH = b"{SWS}/{SWS}".format(**locals())
COLON = b"{SWS}:{SWS}".format(**locals())
ALPHA = b"[a-zA-Z]".format(**locals())
DIGIT = b"[0-9]".format(**locals())
HEXDIG = b"[0-9a-fA-F]".format(**locals())
EQUAL = b"{SWS}={SWS}".format(**locals())
DQUOTE = b"\""
# UTF8_NONASCII = b"" TODO sort out uses.
# alphanum is written out for performance reasons.
# alphanum = "(?:{ALPHA}|{DIGIT})"
alphanum = b"[a-zA-Z0-9]"

# A SIP token.
# token       =  1*(alphanum / "-" / "." / "!" / "%" / "*"
#                      / "_" / "+" / "`" / "'" / "~" )
token = b"[a-zA-Z0-9#-_.!%*+`'~]+".format(**locals())
STAR = b"*"

# Display name
# display-name   =  *(token LWS)/ quoted-string
display_name = b""

# The end of line string used in SIP messages.
EOL = CRLF

# Magic cookie used in branch parameters.
BranchMagicCookie = b"z9hG4bK"

"""
Via               =  ( "Via" / "v" ) HCOLON via-parm *(COMMA via-parm)
via-parm          =  sent-protocol LWS sent-by *( SEMI via-params )
via-params        =  via-ttl / via-maddr
                     / via-received / via-branch
                     / via-extension
via-ttl           =  "ttl" EQUAL ttl
via-maddr         =  "maddr" EQUAL host
via-received      =  "received" EQUAL (IPv4address / IPv6address)
via-branch        =  "branch" EQUAL token
via-extension     =  generic-param
sent-protocol     =  protocol-name SLASH protocol-version
                     SLASH transport
protocol-name     =  "SIP" / token
protocol-version  =  token
transport         =  "UDP" / "TCP" / "TLS" / "SCTP"
                     / other-transport
sent-by           =  host [ COLON port ]
ttl               =  1*3DIGIT ; 0 to 255

quoted-pair  =  "\" (%x00-09 / %x0B-0C
                / %x0E-7F)

SIP-URI          =  "sip:" [ userinfo ] hostport
                    uri-parameters [ headers ]
SIPS-URI         =  "sips:" [ userinfo ] hostport
                    uri-parameters [ headers ]
userinfo         =  ( user / telephone-subscriber ) [ ":" password ] "@"
user             =  1*( unreserved / escaped / user-unreserved )
user-unreserved  =  "&" / "=" / "+" / "$" / "," / ";" / "?" / "/"
password         =  *( unreserved / escaped /
                    "&" / "=" / "+" / "$" / "," )
hostport         =  host [ ":" port ]
host             =  hostname / IPv4address / IPv6reference
hostname         =  *( domainlabel "." ) toplabel [ "." ]
domainlabel      =  alphanum
                    / alphanum *( alphanum / "-" ) alphanum
toplabel         =  ALPHA / ALPHA *( alphanum / "-" ) alphanum
IPv4address    =  1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT "." 1*3DIGIT
IPv6reference  =  "[" IPv6address "]"
IPv6address    =  hexpart [ ":" IPv4address ]
hexpart        =  hexseq / hexseq "::" [ hexseq ] / "::" [ hexseq ]
hexseq         =  hex4 *( ":" hex4)
hex4           =  1*4HEXDIG
port           =  1*DIGIT"""


hex4 = b"{HEXDIG}{{1,4}}".format(**locals())
# Surely IPv6 address length is limited?
hexseq = b"{hex4}(?::{hex4})*".format(**locals())
hexpart = b"(?:{hexseq}|{hexseq}::(?:{hexseq})?|::(?:{hexseq})?)".format(
    **locals())
IPv4address = b"{DIGIT}{{1,3}}(?:[.]{DIGIT}{{1,3}}){{3}}".format(**locals())
IPv6address = b"{hexpart}(?::{IPv4address})?".format(**locals())
IPv6reference = b"[[]{IPv6address}[]]".format(**locals())
port = b"{DIGIT}+".format(**locals())
toplabel = b"(?:{ALPHA}|{ALPHA}(?:{alphanum}|-)*{alphanum})".format(
    **locals())
domainlabel = b"(?:{alphanum}|{alphanum}(?:{alphanum}|-)*{alphanum})".format(
    **locals())
hostname = b"(?:{domainlabel}[.])*{toplabel}[.]?".format(**locals())
host = b"(?:{hostname}|{IPv4address}|{IPv6reference})".format(**locals())
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


class ProtocolError(Exception):
    """Something didn't make sense in SIP."""
    pass


class ProtocolSyntaxError(Exception):
    """Syntax errors are when a request is missing some key bit from the
    protocol, or is otherwise confused. Like trying to build
    a request with a response code.
    """


class ProtocolValueError(ProtocolError):
    """Value errors are when a user request makes syntactic sense, but some
    value is not allowed by the protocol. For example asking for a request
    type of "notarequest" or a status code of "13453514".
    """
    pass


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
