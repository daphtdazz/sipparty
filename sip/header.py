"""header.py

Encapsulates SIP headers.

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import six
import datetime
import random
import re
import logging
import _util
import vb
from parse import Parser
import prot
import components
import field
import pdb

log = logging.getLogger(__name__)


@six.add_metaclass(_util.attributesubclassgen)
@_util.TwoCompatibleThree
class Header(Parser, vb.ValueBinder):
    """A SIP header.

    Each type of SIP header has its own subclass, and so generally the Header
    class is just used as an abstract class. To get an instance of a subclass
    of a particular type, do:

    Header.type()
    # E.g
    Header.accept()
    """

    # The `types` class attribute is used by the attributesubclassgen
    # metaclass to know what types of subclass may be created.
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

    type = _util.ClassType("Header")
    field = _util.FirstListItemProxy("fields")

    parseinfo = {
        Parser.Pattern:
            "^\s*([^:\s]*)\s*:"  # The type.
            "\s*"
            "([^,]+)$"  # Everything else to be parsed in parsecust().
            "".format("|".join([
                _util.attributesubclassgen.NormalizeGeneratingAttributeName(
                    type)
                for type in types])),
        Parser.Constructor:
            (1, lambda type: getattr(Header, type)())
    }

    def parsecust(self, string, mo):

        data = mo.group(2)
        fields = data.split(",")
        log.debug("Header fields: %r", fields)

        if not hasattr(self, "FieldDelegateClass"):
            try:
                self.fields = fields
            except AttributeError:
                log.debug(
                    "Can't set 'fields' on instance of %r.", self.__class__)
            return

        fdc = self.FieldDelegateClass
        if hasattr(fdc, "Parse"):
            create = lambda x: fdc.Parse(x)
        else:
            create = lambda x: fdc(x)

        self.fields = [create(f) for f in fields]

    def __init__(self, fields=None):
        """Initialize a header line.
        """
        super(Header, self).__init__()

        if fields is None:
            fields = list()

        self.__dict__["fields"] = fields

    def __bytes__(self):
        return "{0}: {1}".format(
            self.type, ",".join([str(v) for v in self.fields]))


class FieldDelegateHeader(Header):
    """The FieldDelegateHeader delegates the work to a field class. Useful
    where the correct fields are complex."""

    def __init__(self, *args, **kwargs):
        super(FieldDelegateHeader, self).__init__(*args, **kwargs)
        if not hasattr(self, "field"):
            self.field = self.FieldDelegateClass()

    def __setattr__(self, attr, val):
        if hasattr(self, "field"):
            myval = self.field
            if myval:
                dattrs = myval.delegateattributes
                if attr in dattrs:
                    setattr(myval, attr, val)
                    return

        super(FieldDelegateHeader, self).__setattr__(attr, val)
        return

    def __getattr__(self, attr):
        if attr != "field" and hasattr(self, "field"):
            myval = self.field
            dattrs = myval.delegateattributes
            if attr in dattrs:
                return getattr(myval, attr)
        try:
            return super(FieldDelegateHeader, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} object has no attribute "
                "{attr!r}".format(**locals()))


class ToHeader(FieldDelegateHeader):
    """A To: header"""
    FieldDelegateClass = field.DNameURIField


class FromHeader(FieldDelegateHeader):
    """A From: header"""
    FieldDelegateClass = field.DNameURIField


class ViaHeader(FieldDelegateHeader):
    """The Via: Header."""
    FieldDelegateClass = field.ViaField


class Call_IdHeader(Header):
    """Call ID header."""

    @classmethod
    def GenerateKey(cls):
        """Generate a random alphanumeric key.

        Returns a string composed of 6 random hexadecimal characters, followed
        by a hyphen, followed by a timestamp of form YYYYMMDDHHMMSS.
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
    def field(self):
        fields = self.__dict__["fields"]
        if fields:
            return fields[0]

        if self.key is None:
            self.key = Call_IdHeader.GenerateKey()

        if self.host:
            val = "{self.key}@{self.host}".format(self=self)
        else:
            val = "{self.key}".format(self=self)
        return val

    @property
    def fields(self):
        fields = self.__dict__["fields"]
        if not fields:
            fields = [self.field]
            self.fields = fields
        return fields

    @fields.setter
    def fields(self, fields):
        self.__dict__["fields"] = fields


class CseqHeader(FieldDelegateHeader):
    FieldDelegateClass = field.CSeqField


class Max_ForwardsHeader(FieldDelegateHeader):
    FieldDelegateClass = field.Max_ForwardsField
