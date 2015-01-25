import re
import _util
import prot
from request import Request
from header import Header


class Message(_util.ValueBinder):
    """Generic message class. Use `Request` or `Response` rather than using
    this directly.
    """

    types = Request.types
    __metaclass__ = _util.attributesubclassgen

    bindings = []

    reqattrre = re.compile(
        "({0})request".format("|".join(types)), flags=re.IGNORECASE)
    headerattrre = re.compile(
        "({0})header".format("|".join(Header.types).replace("-", "[_-]")),
        flags=re.IGNORECASE)

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

        super(Message, self).__init__()

        if startline is None:
            try:
                startline = getattr(Request, self.type)()
            except Exception:
                raise

        for prop in ("startline", "headers", "bodies"):
            setattr(self, prop, locals()[prop])

        if autoheader:
            self.autofillheaders()

        self._establishbindings()

    def __str__(self):

        components = [self.startline]
        components.extend(self.headers)
        # Note we need an extra newline between headers and bodies
        components.append("")
        if self.bodies:
            components.extend(self.bodies)
            components.append("")  # need a newline at the end.

        return prot.EOL.join([str(_cp) for _cp in components])

    def __getattr__(self, attr):
        """Get some part of the message. E.g. get a particular header like:
        message.toheader
        """

        reqmo = self.reqattrre.match(attr)
        if reqmo is not None:
            if self.startline.type == mo.group(1):
                return self.startline

        hmo = self.headerattrre.match(attr)
        if hmo is not None:
            canonicalheadername = _util.sipheader(hmo.group(1))
            for header in self.headers:
                if header.type == canonicalheadername:
                    return header

        try:
            return getattr(super(Message, self), attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} object has no attribute "
                "{attr!r}".format(**locals()))

    def _establishbindings(self):

        for binding in self.bindings:
            self.bind(binding[0], binding[1])

    def autofillheaders(self):
        for hdr in self.startline.mandatoryheaders:
            if hdr not in [_hdr.type for _hdr in self.headers]:
                self.headers.append(getattr(Header, hdr)())


class InviteMessage(Message):
    """An INVITE."""

    bindings = [("startline.uri", "toheader.value.uri")]
