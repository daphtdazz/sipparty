"""Components of data that make up SIP messages.
"""
# We import defaults at the bottom, since defaults uses these classes, and so
# they must always be declared before defaults is.
# import defaults
import vb


class Host(vb.ValueBinder):

    def __init__(self, host=None, port=None):
        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

    def __str__(self):

        host = self.host
        port = self.port

        if not port and hasattr(defaults, "useports") and defaults.useports:
            port = defaults.port

        if host and port:
            return "{host}:{port}".format(**locals())

        if self.host:
            return "{host}"

        return ""


class AOR(vb.ValueBinder):
    """A AOR object."""

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


class URI(vb.ValueBinder):
    """A URI object."""

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


class DNameURI(vb.ValueBinder):
    """A display name plus a uri value object"""

    delegateattributes = ["dname", "uri"]

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

    def generate(self):
        pass

import defaults
