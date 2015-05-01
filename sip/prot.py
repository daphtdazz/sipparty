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

# Whitespace, linear, "separator" i.e. optional whitespace.
#  LWS  =  [*WSP CRLF] 1*WSP ; linear whitespace
#  SWS  =  [LWS] ; sep whitespace
CRLF = b"\r\n"
WS = "[ \t]"
LWS = b"(?:%s*%s)?%s+" % (WS, CRLF, WS)
SWS = b"(?:%s)?" % (LWS,)

# A SIP token.
# token       =  1*(alphanum / "-" / "." / "!" / "%" / "*"
#                      / "_" / "+" / "`" / "'" / "~" )
token = b"[\w-.!%*_+`'~]+"

# Display name
# display-name   =  *(token LWS)/ quoted-string
display_name = b""

# The end of line string used in SIP messages.
EOL = CRLF

# Magic cookie used in branch parameters.
BranchMagicCookie = b"z9hG4bK"


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
