"""Components of data that make up SIP messages.
"""
# We import defaults at the bottom, since defaults uses these classes, and so
# they must always be declared before defaults is.
# import defaults
import vb
from parse import Parser


class Host(Parser, vb.ValueBinder):

    parseinfo = {
        Parser.Pattern:
            "([^:]+|[[][:a-fA-F\d]+[]])"
            "(:(\d)+)?$",
        Parser.Mappings:
            [("host",),
             ("port",)],
    }

    def __init__(self, host=None, port=None):
        super(Host, self).__init__()
        self.host = host
        self.port = port

    def __str__(self):

        host = self.host
        port = self.port

        if not port and hasattr(defaults, "useports") and defaults.useports:
            port = defaults.port

        if host and port:
            return "{host}:{port}".format(**locals())

        if self.host:
            return "{host}".format(**locals())

        return ""


class AOR(Parser, vb.ValueBinder):
    """A AOR object."""

    parseinfo = {
        Parser.Pattern:
            "(.*)"
            "@"
            "(.*)$",
        Parser.Mappings:
            [("username",),
             ("host", Host)],
    }

    def __init__(self, username=None, host=None, port=None):
        super(AOR, self).__init__()
        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

    def __str__(self):
        if self.username and self.host:
            return "{username}@{host}".format(**self.__dict__)

        if self.host:
            return "{host}".format(**self.__dict__)

        return ""


class URI(Parser, vb.ValueBinder):
    """A URI object."""

    parseinfo = {
        Parser.Pattern:
            "(sip|sips)"
            ":"
            "(.*)$",
        Parser.Mappings:
            [("scheme",),
             ("aor", AOR)],
    }

    def __init__(self, scheme=None, aor=None):
        super(URI, self).__init__()

        if scheme is None:
            scheme = defaults.scheme
        if aor is None:
            aor = AOR()

        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

    def __str__(self):
        return "{scheme}:{aor}".format(**self.__dict__)


class DNameURI(Parser, vb.ValueBinder):
    """A display name plus a uri value object"""

    delegateattributes = ["dname", "uri"]

    dname_mapping = ("dname", None, lambda x: x.strip())
    uri_mapping = ("uri", URI)
    parseinfo = {
        Parser.Pattern:
            "("  # Either we want...
            "([^<]+)"  # something which is not in angle brackets (disp. name)
            "<([^>]+)>|"  # followed by a uri that is in <> OR...
            "("
            "(\w.*)\s+|"  # optionally at least one non-space for the disp
            "\s*"  # or just spaces
            ")"
            "([^\s]+)"  # at least one thing that isn't a space for the uri
            "\s*"  # followed by arbitrary space
            ")$",
        Parser.Mappings:
            [None,
             dname_mapping,
             uri_mapping,
             None,
             dname_mapping,
             uri_mapping]
    }

    def __init__(self, dname=None, uri=None):
        super(DNameURI, self).__init__()

        if uri is None:
            uri = URI()

        self.dname = dname
        self.uri = uri

    def __str__(self):
        if self.dname and self.uri:
            return("\"{self.dname}\" <{self.uri}>".format(**locals()))

        if self.uri:
            return(str(self.uri))

        return ""

import defaults