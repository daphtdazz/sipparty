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
import datetime
import random
import re
import logging
from six import (binary_type as bytes, add_metaclass)
from numbers import Integral
from sipparty import (util, vb, Parser)
from sipparty.deepclass import (DeepClass, dck)
import prot
from prot import Incomplete
import components
from field import (DNameURIField, ViaField)
from request import Request
import defaults

log = logging.getLogger(__name__)


@add_metaclass(util.attributesubclassgen)
@util.TwoCompatibleThree
class Header(
        DeepClass("_hdr_", {
            "header_value": {dck.gen: lambda: None},
            "type": {dck.descriptor: lambda x: util.ClassType("Header")}
            }),
        Parser, vb.ValueBinder):
    """A SIP header.

    Each type of SIP header has its own subclass, and so generally the Header
    class is just used as an abstract class. To get an instance of a subclass
    of a particular type, do:

    Header.<type name case insensitive>()
    # E.g
    Header.accept()
    >> AcceptHeader()
    Hader.INVITE()
    >> InviteHeader()
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

    parseinfo = {
        Parser.Pattern:
            # The type. Checked in the constructor whether it's a valid header
            # or not.
            "({header_value})"  # Everything else to be parsed in parsecust().
            "".format(**prot.__dict__),
        Parser.Mappings:
            [("header_value",)]
    }

    def _hdr_prepend(self):
        return b"{0.type}:".format(self)


class FieldsBasedHeader(
        DeepClass("_dnurh_", {
            "fields": {dck.gen: list, dck.descriptor: None},
            "field": {
                dck.descriptor: lambda x: util.FirstListItemProxy("fields"),
                dck.gen: "GenerateField"}
        }),
        Header):

    @classmethod
    def GenerateField(cls):
        return cls.FieldClass()

    def parsecust(self, string, mo):
        data = mo.group(1)
        log.debug("Header fields data: %r", data)

        if not hasattr(self, "FieldClass") or self.FieldClass is None:
            raise AttributeError(
                "%r instance has no FieldClass defined, so cannot be a field "
                "based header." % (self.__class__.__name__,))

        fdc = self.FieldClass
        flds = fdc.Parse(data)

        if not isinstance(flds, list):
            raise ValueError(
                "%r field class did not return a list of fields from its "
                "Parse method. You can use the Parser.Repeats key in the "
                "parser dictionary to create lists automatically." % (
                    self.FieldClass.__name__))

        self.fields = flds

    def __bytes__(self):
        flds = self.fields
        if len(flds) == 0:
            raise Incomplete('Header type %r has no fields.' % (
                self.__class__.__name__,))
        try:
            return b"{0} {1}".format(
                self._hdr_prepend(), ",".join([bytes(v) for v in self.fields]))
        except Incomplete as exc:
            exc.args += ('Header type %r' % self.__class__.__name__,)
            raise


class DNameURIHeader(FieldsBasedHeader):
    FieldClass = DNameURIField
    vb_dependencies = (
        ("field", (
            "uri", "displayname", "aor", "username", "host", "address",
            "port", "parameters")),
    )


class ToHeader(DNameURIHeader):
    """A To: header"""


class FromHeader(DNameURIHeader):
    """A From: header"""


class ViaHeader(FieldsBasedHeader):
    """The Via: Header."""
    FieldClass = ViaField
    vb_dependencies = (
        ("field", (
            "host", "address", "port", "parameters")),
    )


class ContactHeader(
        DeepClass("_ctcth_", {
            "isStar": {
                dck.check: lambda x: x is True or x is False,
                dck.gen: lambda: False},

            }),
        DNameURIHeader):
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

    def __bytes__(self):
        log.debug("bytes(ContactHeader)")
        if self.isStar:
            return b"{0} {1}".format(self._hdr_prepend(), prot.STAR)
        return super(ContactHeader, self).__bytes__()


class Call_IdHeader(
        DeepClass("_cidh_", {
            "host": {},
            "key": {dck.gen: "GenerateKey"}
            }),
        Header):
    """Call ID header.

    To paraphrase:

    https://tools.ietf.org/html/rfc3261#section-8.1.1.4

    This value should be generated uniquely over space and time for each new
    dialogue initiated by the UA. It must be the same for all messages during
    a dialogue. It SHOULD also be the same for each REGISTER sent to maintain a
    registration by the UA. I.e. being registered => being in a dialogue.
    """

    parseinfo = {
        Parser.Pattern:
            "(.*)$",  # No parameters.
        Parser.Mappings:
            [("key",)]
    }

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

    @property
    def value(self):
        key = self.key
        if not key:
            return None

        host = self.host
        if host:
            return b"{0.key}@{0.host}".format(self)

        return b"{0.key}".format(self)

    def __bytes__(self):
        val = self.value
        if val is None:
            raise Incomplete("Call ID header has no key.")
        return b"{0} {1}".format(self._hdr_prepend(), val)


class CseqHeader(
        DeepClass("_csh_", {
            "number": {
                dck.gen: lambda: random.randint(0, 2**31 - 1),
                dck.check: lambda num: isinstance(num, Integral)},
            "reqtype": {dck.gen: lambda: None}
        }),
        Header):

    parseinfo = {
        Parser.Pattern:
            "(\d+)"
            " "
            "([\w_-]+)$",  # No parameters.
        Parser.Mappings:
            [("number", int),
             ("reqtype", None, lambda x: getattr(Request.types, x))]
    }

    def __bytes__(self):

        if self.reqtype is None:
            raise Incomplete

        return b"%s %d %s" % (
            self._hdr_prepend(), self.number, self.reqtype)


class Max_ForwardsHeader(
        DeepClass("_mfh_", {
            "number": {
                dck.gen: lambda: defaults.max_forwards,
                dck.check: lambda x: isinstance(x, Integral)}
            }),
        Header):

    parseinfo = {
        Parser.Pattern:
            "(\d+)$",  # No parameters.
        Parser.Mappings:
            [("number", int)]
    }

    def __bytes__(self):
        return "{0} {1.number}".format(self._hdr_prepend(), self)

Header.addSubclassesFromDict(locals())
