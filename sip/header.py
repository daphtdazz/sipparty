import datetime
import random
import _util
import prot
import field
import pdb


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

        self.__dict__["values"] = values

    def __str__(self):
        return "{0}: {1}".format(
            self.type, ",".join([str(v) for v in self.values]))

    @property
    def type(self):
        class_name = self.__class__.__name__
        type = class_name.replace("Header", "")
        return type

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


class FieldDelegateHeader(Header):
    """The FieldDelegateHeader delegates the work to a field class. Useful
    where the correct values are complex."""

    def __init__(self, *args, **kwargs):
        super(FieldDelegateHeader, self).__init__(*args, **kwargs)
        if not hasattr(self, "value"):
            self.value = self.FieldDelegateClass()

    def __setattr__(self, attr, val):
        if hasattr(self, "value"):
            myval = self.value
            if myval:
                dattrs = myval.delegateattributes
                if attr in dattrs:
                    setattr(myval, attr, val)
                    return

        super(FieldDelegateHeader, self).__setattr__(attr, val)
        return

    def __getattr__(self, attr):
        if attr != "value" and hasattr(self, "value"):
            myval = self.value
            dattrs = myval.delegateattributes
            if attr in dattrs:
                return getattr(myval, attr)
        return super(FieldDelegateHeader, self).__getattr__(attr)


class ToHeader(FieldDelegateHeader):
    """A To: header"""
    FieldDelegateClass = prot.DNameURI


class FromHeader(FieldDelegateHeader):
    """A From: header"""
    FieldDelegateClass = prot.DNameURI


class ViaHeader(FieldDelegateHeader):
    """The Via: Header, possibly THE most important header."""
    FieldDelegateClass = field.ViaField


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

    def __init__(self, *args, **kwargs):
        Header.__init__(self, *args, **kwargs)
        self.host = None
        self.key = None

    @property
    def value(self):
        if self.key is None:
            self.key = Call_IdHeader.GenerateKey()

        if self.host:
            val = "{self.key}@{self.host}".format(self=self)
        else:
            val = "{self.key}".format(self=self)
        return val

    @property
    def values(self):
        return [self.value]
