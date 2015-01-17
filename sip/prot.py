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

    def __init__(self, username, host):

        for prop in ("username", "host"):
            setattr(self, prop, locals()[prop])

    def __str__(self):
        return "{username}@{host}".format(**self.__dict__)


def HeaderForName(headername, *args, **kwargs):
    return(Header.FindSubClass(headername)(*args, **kwargs))


class Header(object):
    """A SIP header."""

    types = _util.Enum(
        ("Accept", "Accept-Encoding", "Accept-Language", "Alert-Info", "Allow",
         "Authentication-Info", "Authorization", "Call-ID", "Call-Info",
         "Contact", "Content-Disposition", "Content-Encoding",
         "Content-Language", "Content-Length", "Content-Type", "CSeq", "Date",
         "Error-Info", "Expires", "From", "In-Reply-To", "Max-Forwards",
         "Min-Expires", "MIME-Version", "Organization", "Priority",
         "Proxy-Authenticate", "Proxy-Authorization", "Proxy-Require",
         "Record-Route", "Reply-To", "Require", "Retry-To", "Route", "Server",
         "Subject", "Supported", "Timestamp", "To", "Unsupported",
         "User-Agent", "Via", "Warning", "WWW-Authenticate"),
        normalize=_util.sipheader)

    # This allows us to generate instances of subclasses by class attribute
    # access, so Header.accept creates an accept header etc.
    __metaclass__ = _util.attributesubclassgen

    def __init__(self, values=[]):
        """Initialize a header line.
        """
        for prop in ("values",):
            setattr(self, prop, locals()[prop])

    def __str__(self):
        self.generatevalues()
        return "{0}: {1}".format(self.type, ",".join(self.values))

    def generatevalues(self):
        """Subclasses should implement this to generate values dynamically (if
        possible)"""
        pass


class ToHeader(Header):
    """A To: header"""


class Call_IdHeader(Header):
    """Call ID header."""

    @classmethod
    def GenerateKey(cls):
        """Generate a random alphanumeric key.

        Returns a string composed of 6 random hexadecimal characters, followed
        by a hypen, followed by a timestamp of form YYYYMMDDHHMMSS.
        """
        keyval = random.randint(0, 2**24 - 1)

        dt = datetime.datetime.now()
        keydate = (
            "{dt.year:04}{dt.month:02}{dt.day:02}{dt.hour:02}{dt.minute:02}"
            "{dt.second:02}".format(dt=dt))

        return "{keyval:06x}-{keydate}".format(**locals())


    def __init__(self, values=[]):
        Header.__init__(self, values)
        self.host = None
        self.key = None

    def generatevalues(self):
        if not self.values or not self.values[0]:
            if self.key:
                key = self.key
            else:
                key = self.__class__.GenerateKey()

            if self.host:
                genval = "{key}@{self.host}".format(**locals())
            else:
                genval = "{key}".format(**locals())

            self.values = [genval]


class Request(object):
    """Enumeration class generator"""

    types = _util.Enum(
        ("ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"),
        normalize=_util.upper)

    mandatoryheaders = (
        Header.types.From,  Header.types.To, Header.types.Via,
        Header.types.call_id, Header.types.cseq, Header.types.max_forwards)
    shouldheaders = ()  # Should be sent but parties must cope without.
    conditionalheaders = ()
    optionalheaders = (
        Header.types.authorization, Header.types.content_disposition,
        Header.types.content_encoding, Header.types.content_language,
        Header.types.content_type)
    streamheaders = (  # Required to be sent with stream-based protocols.
        Header.types.content_length,)
    bodyheaders = None  # Required with non-empty bodies.
    naheaders = None  # By default the complement of the union of the others.

    # This gives me case insensitive subclass instance creation and type-
    # checking.
    __metaclass__ = _util.attributesubclassgen

    def __str__(self):
        return "{type} {aor} {protocol}".format(**self.__dict__)

    def __init__(self, aor=None, protocol=defaults.sipprotocol):
        for prop in ("aor", "protocol"):
            setattr(self, prop, locals()[prop])
        self.type = self.type


class InviteRequest(Request):
    type = Request.types.invite


class Message(object):
    """Generic message class. Use `Request` or `Response` rather than using
    this directly.
    """

    types = Request.types
    __metaclass__ = _util.attributesubclassgen

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

        return EOL.join([str(_cp) for _cp in components])

    def autofillheaders(self):
        for hdr in self.startline.mandatoryheaders:
            if hdr not in [_hdr.type for _hdr in self.headers]:
                self.headers.append(getattr(Header, hdr)())


class InviteMessage(Message):
    """An INVITE."""
