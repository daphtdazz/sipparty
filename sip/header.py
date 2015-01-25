import datetime
import random
import _util


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
