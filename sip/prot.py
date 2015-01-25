"""Parse and build SIP messages"""
import collections
import random
import datetime
import defaults
import _util
import pdb

EOL = "\r\n"


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


class AOR(object):
    """A AOR object."""

    def __init__(self, username, host, port=None):
        for prop in ("username", "host", "port"):
            setattr(self, prop, locals()[prop])

    def __str__(self):
        return "{username}@{host}".format(**self.__dict__)


class URI(_util.ValueBinder):
    """A URI object."""

    def __init__(self, scheme=defaults.scheme, aor=None):
        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

    def __str__(self):
        return "{scheme}:{aor}".format(**self.__dict__)


class DNameURI(_util.ValueBinder):
    """A display name plus a uri value object"""

    def __init__(self, dname=None, uri=None):
        super(DNameURI, self).__init__()

        if uri is None:
            uri = URI()

        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

    def __str__(self):
        if self.dname and self.uri:
            return("\"{self.dname}\" <{self.uri}>".format(**locals()))

        if self.uri:
            return(str(self.uri))

        return ""
