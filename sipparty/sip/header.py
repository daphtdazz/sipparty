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
from datetime import datetime
from collections import OrderedDict
import logging
from numbers import Integral
from random import randint
from six import (add_metaclass, binary_type as bytes, PY2)
from ..deepclass import (DeepClass, dck)
from ..parse import (Parser,)
from ..util import (
    abytes, astr, attributesubclassgen, BytesGenner, ClassType,
    FirstListItemProxy, TwoCompatibleThree,)
from ..vb import ValueBinder
from . import defaults
from .field import (DNameURIField, ViaField)
from .param import Parameters
from .prot import (bdict, Incomplete, HeaderTypes)
from .request import Request

log = logging.getLogger(__name__)


@add_metaclass(attributesubclassgen)
@TwoCompatibleThree
class Header(
        DeepClass("_hdr_", {
            "header_value": {dck.gen: lambda: None}
        }),
        Parser, BytesGenner, ValueBinder):
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
    types = HeaderTypes.enum()
    type = ClassType('Header')

    parseinfo = {
        Parser.Pattern:
            # The type. Checked in the constructor whether it's a valid header
            # or not.
            b"(%(header_value)s)"  # Everything else parsed in parsecust().
            b"" % bdict,
        Parser.Mappings:
            [("header_value",)]
    }

    def _hdr_prepend(self):
        if PY2:
            return b'%s: ' % self.type

        return b'%s: ' % abytes(self.type)


class FieldsBasedHeader(
        DeepClass("_dnurh_", OrderedDict((
            ("fields", {dck.gen: list, dck.descriptor: None}),
        ))),
        Header):

    @classmethod
    def GenerateField(cls):
        return cls.FieldClass()

    field = FirstListItemProxy("fields")

    def __init__(self, **kwargs):
        super(FieldsBasedHeader, self).__init__(**kwargs)
        if getattr(self, 'field', None) is None:
            self.field = self.GenerateField()

    def parsecust(self, string, mo):
        data = self.header_value
        log.debug("Header fields data: %r", data)

        fdc = getattr(self, 'FieldClass', None)
        if fdc is None:
            raise AttributeError(
                "%r instance has no FieldClass defined, so cannot be a field "
                "based header." % (self.__class__.__name__,))

        flds = fdc.Parse(data)
        log.debug('Parsed fields: %r', flds)

        if not isinstance(flds, list):
            raise ValueError(
                "%r field class did not return a list of fields from its "
                "Parse method. You can use the Parser.Repeats key in the "
                "parser dictionary to create lists automatically." % (
                    self.FieldClass.__name__))

        self.fields = flds

    def bytesGen(self):
        flds = self.fields
        if len(flds) == 0:
            raise Incomplete('Header type %r has no fields.' % (
                self.__class__.__name__,))
        try:
            yield self._hdr_prepend()
            first_field = True
            for fld in self.fields:
                if not first_field:
                    yield b','
                    first_field = False

                for bs in fld.safeBytesGen():
                    yield bs

        except Incomplete as exc:
            exc.args = (
                (exc.args[0] + '; Header type %r' % self.__class__.__name__,) +
                exc.args[1:])

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
            "transport", "protocol", "host", "address", "port", "parameters")),
    )


class ContactHeader(
        DeepClass("_ctcth_", {
            "isStar": {
                dck.check: lambda x: x is True or x is False,
                dck.gen: lambda: False},

        }, recurse_repr=True),
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

    parseinfo = {
        Parser.Pattern:
            # The type. Checked in the constructor whether it's a valid header
            # or not.
            b"(?:(%(STAR)s)|(%(header_value)s))"
            b"" % bdict,
        Parser.Mappings:
            [("isStar", bool),
             ("header_value",)]
    }

    def parsecust(self, string, mo):
        log.debug('%s instance parsecust %r', self.__class__.__name__, string)
        if self.isStar:
            log.debug('is_star')
            return

        super(ContactHeader, self).parsecust(string, mo)
        log.debug('%s instance: %r', self.__class__.__name__, self)

    def bytesGen(self):
        log.debug("bytes(ContactHeader)")
        if self.isStar:
            yield self._hdr_prepend()
            yield b'*'
            return

        for bs in super(ContactHeader, self).bytesGen():
            yield bs


class Call_IdHeader(  # noqa
        DeepClass("_cidh_", {
            "host": {},
            "key": {
                dck.gen: "GenerateKey",
                dck.check: lambda x: isinstance(x, bytes)}
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
            b"(.*)$",  # No parameters.
        Parser.Mappings:
            [("key",)]
    }

    @classmethod
    def GenerateKey(cls):
        """Generate a random alphanumeric key.

        Returns a string composed of 6 random hexadecimal characters, followed
        by a hyphen, followed by a timestamp of form YYYYMMDDHHMMSS.
        """
        keyval = randint(0, 2 ** 24 - 1)

        dt = datetime.now()
        keydate = (
            b"%(year)04d%(month)02d%(day)02d%(hour)02d%(minute)02d"
            b"%(second)02d" % {
                abytes(key): getattr(dt, key) for key in (
                    'year', 'month', 'day', 'hour', 'minute', 'second'
                )
            })

        return b"%06x-%s" % (keyval, keydate)

    @property
    def value(self):
        key = self.key
        if not key:
            return None

        host = self.host
        if host:
            return b"%s@%s" % (self.key, self.host)

        return b"%s" % (self.key)

    def bytesGen(self):
        yield self._hdr_prepend()
        if self.key is None:
            raise Incomplete("Call ID header has no key.")
        yield self.key
        if self.host:
            yield b'@'
            yield bytes(self.host)


class CseqHeader(
        DeepClass("_csh_", {
            "number": {
                # https://tools.ietf.org/html/rfc3261#section-12.2.1.1 says
                # that the CSeq should never wrap and be a 32 bit unsigned
                # integer. Therefore start from a random value up to half the
                # 32 bit space to ensure we are really unlikely to wrap, even
                # if we get the largest possible starting number.
                dck.gen: lambda: randint(0, 2 ** 31 - 1),
                dck.check: lambda num: (
                    isinstance(num, Integral) and 0 <= num < 2 ** 32)},
            "reqtype": {dck.gen: lambda: None}
        }),
        Header):

    parseinfo = {
        Parser.Pattern:
            b"(\d+)"
            b" "
            b"([\w_-]+)$",  # No parameters.
        Parser.Mappings:
            [("number", int),
             ("reqtype", lambda x: getattr(Request.types, astr(x)))]
    }

    def bytesGen(self):

        if self.reqtype is None:
            raise Incomplete("CSeqHeader has no request type.")

        yield self._hdr_prepend()
        yield b'%d' % self.number
        yield b' '
        yield abytes(self.reqtype)


class NumberHeader(
        DeepClass("_numh_", {
            "number": {
                dck.gen: "Default_Number",
                dck.check: lambda x: isinstance(x, Integral)}
        }),
        Header):
    parseinfo = {
        Parser.Pattern:
            b"(\d+)$",  # No parameters.
        Parser.Mappings:
            [("number", int)]
    }

    def bytesGen(self):
        yield self._hdr_prepend()
        yield b'%d' % self.number


class Max_ForwardsHeader(NumberHeader):  # noqa
    Default_Number = defaults.max_forwards


class Content_LengthHeader(NumberHeader):  # noqa
    Default_Number = 0


class Content_TypeHeader(  # noqa
        DeepClass("_cth_", {
            "content_type": {},
            "parameters": {dck.gen: Parameters}
        }),
        Header):
    """ABNF:

    m-type SLASH m-subtype *(SEMI m-parameter)
    """

    parseinfo = {
        Parser.Pattern:
            b"(%(m_type)s%(SLASH)s%(m_subtype)s)((?:%(SEMI)s%(m_parameter)s)*)"
            b"" % bdict,  # No parameters.
        Parser.Mappings:
            [("content_type",),
             ("parameters", Parameters)]
    }

    def bytesGen(self):
        yield self._hdr_prepend()
        if not self.content_type:
            raise Incomplete("Content Header has no type.")

        yield bytes(self.content_type)
        for bs in self.parameters.safeBytesGen():
            yield bs

Header.addSubclassesFromDict(locals())
