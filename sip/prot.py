"""This module contains details on the SIP protocol, and should generally not
require any of the other sip specific code."""
import _util

# The end of line string used in SIP messages.
EOL = "\r\n"

# Magic cookie used in branch parameters.
BranchMagicCookie = "z9hG4bK"


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
