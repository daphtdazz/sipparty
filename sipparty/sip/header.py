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

from sipparty import (util, vb, Parser)
import prot
import components
import field

log = logging.getLogger(__name__)
bytes = six.binary_type


@six.add_metaclass(
    # The FSM type needs both the attributesubclassgen and the cumulative
    # properties metaclasses.
    type('HeaderType',
         (util.CCPropsFor(("fields",)),
          util.attributesubclassgen),
         dict()))
@util.TwoCompatibleThree
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
    types = util.Enum(
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
        normalize=util.sipheader)

    type = util.ClassType("Header")
    field = util.FirstListItemProxy("fields")
    fields = util.DerivedProperty(
        "_hdr_fields", check=lambda x: isinstance(x, list))

    parseinfo = {
        Parser.Pattern:
            # The type. Checked in the constructor whether it's a valid header
            # or not.
            "({token})"
            "{HCOLON}"
            "({header_value})"  # Everything else to be parsed in parsecust().
            "".format(**prot.__dict__),
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
        self.__dict__["_hdr_fields"] = []
        super(Header, self).__init__()

        if fields is None:
            fields = list()

        self.fields = fields

    def __bytes__(self):
        return b"{0}: {1}".format(
            self.type, ",".join([bytes(v) for v in self.fields]))

    def __repr__(self):
        return (
            "{0.__class__.__name__}(fields={0.fields!r})"
            "".format(self))


class FieldDelegateHeader(Header):
    """The FieldDelegateHeader delegates the work to a field class. Useful
    where the correct fields are complex."""

    def __init__(self, *args, **kwargs):
        super(FieldDelegateHeader, self).__init__(*args, **kwargs)
        if not self.fields:
            self.fields = [self.FieldDelegateClass()]

    def __setattr__(self, attr, val):
        if len(self.fields) > 0:
            myval = self.fields[0]
            if hasattr(myval, "delegateattributes"):
                dattrs = myval.delegateattributes
                if attr in dattrs:
                    setattr(myval, attr, val)
                    return

        super(FieldDelegateHeader, self).__setattr__(attr, val)
        return

    def __getattr__(self, attr):
        if len(self.fields) > 0:
            myval = self.fields[0]
            dattrs = myval.delegateattributes
            if attr in dattrs:
                return getattr(myval, attr)
        try:
            return super(FieldDelegateHeader, self).__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} object has no attribute "
                "{attr!r}.".format(**locals()))


class ToHeader(FieldDelegateHeader):
    """A To: header"""
    FieldDelegateClass = field.DNameURIField


class FromHeader(FieldDelegateHeader):
    """A From: header"""
    FieldDelegateClass = field.DNameURIField


class ViaHeader(FieldDelegateHeader):
    """The Via: Header."""
    FieldDelegateClass = field.ViaField


class ContactHeader(FieldDelegateHeader):
    """ABNF from RFC3261:
    Contact        =  ("Contact" / "m" ) HCOLON
                      ( STAR / (contact-param *(COMMA contact-param)))
    contact-param  =  (name-addr / addr-spec) *(SEMI contact-params)
    name-addr      =  [ display-name ] LAQUOT addr-spec RAQUOT
    addr-spec      =  SIP-URI / SIPS-URI / absoluteURI
    display-name   =  *(token LWS)/ quoted-string

    contact-params     =  c-p-q / c-p-expires
                          / contact-extension
    c-p-q              =  "q" EQUAL qvalue
    c-p-expires        =  "expires" EQUAL delta-seconds
    contact-extension  =  generic-param
    delta-seconds      =  1*DIGIT
    """

    # Fields is a cumulative DerivedProperty attribute, so we can update it
    # here with a custom getter.
    fields = util.DerivedProperty(get="_hdrctc_fields")

    isStar = util.DerivedProperty(
        "_hdrctct_isStar", lambda x: x is True or x is False)
    FieldDelegateClass = field.DNameURIField

    def __init__(self, *args, **kwargs):
        self.__dict__["_hdrctct_isStar"] = False
        super(ContactHeader, self).__init__(*args, **kwargs)

    def _hdrctc_fields(self, underlying):

        if self._hdrctct_isStar:
            return (prot.STAR,)

        return underlying


class Call_IdHeader(Header):
    """Call ID header.

    To paraphrase:

    https://tools.ietf.org/html/rfc3261#section-8.1.1.4

    This value should be generated uniquely over space and time for each new
    dialogue initiated by the UA. It must be the same for all messages during
    a dialogue. It SHOULD also be the same for each REGISTER sent to maintain a
    registration by the UA. I.e. being registered == being in a dialogue.
    """

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

    fields = util.DerivedProperty(get="_hdrcid_fields")
    host = util.DerivedProperty("_hdrcid_host")
    key = util.DerivedProperty("_hdrcid_key")

    def __init__(self, *args, **kwargs):
        self.__dict__["_hdrcid_host"] = None
        self.__dict__["_hdrcid_key"] = None
        Header.__init__(self, *args, **kwargs)

    def _hdrcid_fields(self, underlying):
        if underlying:
            return underlying

        if not self.key:
            self.key = Call_IdHeader.GenerateKey()

        if self.host:
            field_text = "{self.key}@{self.host}".format(**locals())
        else:
            field_text = "{self.key}".format(**locals())

        return [field_text]


class CseqHeader(FieldDelegateHeader):
    FieldDelegateClass = field.CSeqField


class Max_ForwardsHeader(FieldDelegateHeader):
    FieldDelegateClass = field.Max_ForwardsField

Header.addSubclassesFromDict(locals())
