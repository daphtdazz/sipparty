"""Parse and build SIP messages"""
import defaults
import _util
import pdb

EOL = "\r\n"


class ProtocolError(Exception):
    pass


class requesttype(object):
    """Enumeration class generator"""

    Types = ("INVITE", "BYE", "REGISTER")
    __metaclass__ = _util.attributetomethodgenerator

    @classmethod
    def generateobjectfromname(cls, method):
        return requesttype(method.upper())

    def __str__(self):
        return "{type}".format(**self.__dict__)

    def __init__(self, type):
        if type not in self.Types:
            raise ProtocolError("No such SIP request type {0}".format(type))

        self.type = type


class URL(object):
    """A URL object."""

    def __init__(self, username, host):

        for prop in ("username", "host"):
            setattr(self, prop, locals()[prop])

    def __str__(self):
        return "{username}@{host}".format(**self.__dict__)


class RequestLine(object):
    """The request line for a request message."""

    def __init__(self, method, targeturl, protocol=defaults.sipprotocol):
        """Init a request line object."""

        for prop in ("method", "targeturl", "protocol"):
            setattr(self, prop, locals()[prop])

    def __str__(self):
        return ("{method} {targeturl} {protocol}" + EOL).format(
            **self.__dict__)
