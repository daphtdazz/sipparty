import _util
import prot
from request import Request
from header import Header


class Message(object):
    """Generic message class. Use `Request` or `Response` rather than using
    this directly.
    """

    types = Request.types
    __metaclass__ = _util.attributesubclassgen

    bindings = []

    @classmethod
    def requestname(cls):
        if not cls.isrequest():
            raise AttributeError(
                "{cls.__name__!r} is not a request so has no request name."
                .format(**locals()))

        return cls.__name__.replace("Message", "")

    @classmethod
    def isrequest(cls):
        return not cls.isresponse()

    @classmethod
    def isresponse(cls):
        return cls.__name__.find("Response") != -1

    def __init__(self, startline=None, headers=[], bodies=[],
                 autoheader=True):
        """Initialize a `Message`."""

        if not startline:
            try:
                startline = getattr(Request, self.type)()
            except Exception:
                raise

        for prop in ("startline", "headers", "bodies"):
            setattr(self, prop, locals()[prop])

        if autoheader:
            self.autofillheaders()

    def __str__(self):

        components = [self.startline]
        components.extend(self.headers)
        # Note we need an extra newline between headers and bodies
        components.append("")
        if self.bodies:
            components.extend(self.bodies)
            components.append("")  # need a newline at the end.

        return prot.EOL.join([str(_cp) for _cp in components])

    def autofillheaders(self):
        for hdr in self.startline.mandatoryheaders:
            if hdr not in [_hdr.type for _hdr in self.headers]:
                self.headers.append(getattr(Header, hdr)())


class InviteMessage(Message):
    """An INVITE."""

    bindings = ["startline.aor", ""]
