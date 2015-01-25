import datetime
import random
import _util
import prot


class Header(_util.ValueBinder):
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

    def __init__(self, values=None):
        """Initialize a header line.
        """
        super(Header, self).__init__()

        if values is None:
            values = list()

        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

        self.generatevalues()

    def __str__(self):
        self.generatevalues()
        return "{0}: {1}".format(
            self.type, ",".join([str(v) for v in self.values]))

    @property
    def value(self):
        if len(self.values) == 0:
            raise AttributeError(
                "{self.__class__.__name__!r} has no attribute 'value'".format(
                    **locals()))
        return self.values[0]

    @value.setter
    def value(self, val):
        if len(self.values) == 0:
            self.values.append(val)
        else:
            self.values[0] = val

    def generatevalues(self):
        """Subclasses should implement this to generate values dynamically (if
        possible)"""
        pass


class ToHeader(Header):
    """A To: header"""

    def generatevalues(self):
        if not hasattr(self, "value"):
            self.value = prot.DNameURI()


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

    def __init__(self, values=None):
        self.host = None
        self.key = None
        if values is None:
            values = list()
        Header.__init__(self, values)

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
