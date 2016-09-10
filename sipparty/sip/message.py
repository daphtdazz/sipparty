"""message.py

Contains classes to build and manipulate SIP messages.

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
from collections import OrderedDict
import logging
from numbers import (Integral)
import re
from six import (add_metaclass, binary_type as bytes, iteritems, next)
from six.moves import reduce
from .. import (util,)
from ..classmaker import classbuilder
from ..deepclass import (DeepClass, dck)
from ..parse import (ParseError,)
from ..sdp import sdpsyntax
from ..transport import SOCK_TYPE_IP_NAMES
from ..util import (astr, BytesGenner, profile)
from ..vb import (KeyTransformer, ValueBinder)
from .body import Body
from .header import Header
from .param import Param
from .prot import bdict
from .request import Request
from .response import Response

log = logging.getLogger(__name__)
ContentLengthBinding = (
    "bodies", "Content_LengthHeader.number", {
        KeyTransformer: lambda bodies: reduce(
            lambda x, y: x + y, [
                summand
                for lst in (
                    [0], [
                        len(bd.content) for bd in bodies
                    ]
                )
                for summand in lst
            ]
        )
    })
ContentTypeBinding = (
    "bodies", "Content_TypeHeader.content_type", {
        KeyTransformer: lambda bodies: (
            None if not bodies else bodies[0].type
        )
    }
)


class UnparsedHeader:
    __slots__ = ['type', 'contents']

    def __init__(self, type, contents):
        self.type = type
        self.contents = contents


@util.TwoCompatibleThree
@classbuilder(
    bases=(
        DeepClass("_msg_", OrderedDict((
            ("startline", {dck.gen: "MakeStartline"}),
            ("headers", {dck.gen: lambda: []}),
            ("bodies", {
                dck.gen: lambda: [], dck.set: "setBodies"}),
            ("parsedBytes", {dck.check: lambda x: isinstance(x, Integral)})
        ))),
        BytesGenner, ValueBinder
    ),
    mc=(
        util.CCPropsFor((
            "mandatoryheaders", "mandatoryparameters", "field_bindings")),
        util.attributesubclassgen)
)
class Message:
    """Generic message class. Use `Request` or `Response` rather than using
    this directly.
    """

    types = Request.types

    mandatoryheaders = [
        Header.types.From, Header.types.To, Header.types.Via,
        Header.types.call_id, Header.types.cseq, Header.types.max_forwards,
        Header.types.content_length]
    shouldheaders = []  # Should be sent but parties must cope without.
    conditionalheaders = []
    optionalheaders = [
        Header.types.authorization, Header.types.content_disposition,
        Header.types.content_encoding, Header.types.content_language,
        Header.types.content_type]
    streamheaders = [  # Required to be sent with stream-based protocols.
        Header.types.content_length]
    bodyheaders = []  # Required with non-empty bodies.
    naheaders = []  # By default the complement of the union of the others.

    mandatoryparameters = {}

    reqattrre = re.compile(
        "(%s)request" % (types.REPattern(),), flags=re.IGNORECASE)

    headerattrre = re.compile(
        "(%s)Header" % Header.types.REPattern().replace(
            "-", "[-_]"), flags=re.IGNORECASE)
    type = util.ClassType("Message")

    MethodRE = re.compile(b"%(Method)s" % bdict)
    ResponseRE = re.compile(b"%(SIP_Version)s" % bdict)
    HeaderSeparatorRE = re.compile(
        b"(%(CRLF)s(?:(%(token)s)%(COLON)s|%(CRLF)s))" % bdict)

    body = util.FirstListItemProxy("bodies")

    field_bindings = [
        ContentLengthBinding,
        ContentTypeBinding
    ]

    @classmethod
    def Parse(cls, string):

        lines = cls.HeaderSeparatorRE.split(string)
        log.detail("Header split: %r", lines)
        line_iter = iter(lines)
        startline = next(line_iter)
        used_bytes = len(startline)
        if cls.ResponseRE.match(startline):
            log.debug("Attempt Message Parse of %r as a response.", startline)
            reqline = Response.Parse(startline)
            log.debug(reqline)
            message = MessageResponse(
                startline=reqline, configure_bindings=False)
            log.debug("Success. Type: %r.", message.type)

        elif cls.MethodRE.match(startline):
            log.debug("Attempt Message Parse of request %r.", startline)
            requestline = Request.Parse(startline)
            message = getattr(Message, requestline.type)(
                startline=requestline, autofillheaders=False,
                configure_bindings=False)
            log.debug("Message is of type %r", message.type)
        else:
            raise ParseError(
                "Startline is not a SIP startline: %r." % (startline,))

        def HNameContentsGen(hcit):
            try:
                while True:
                    hnamebytes = len(next(hcit))
                    hname = next(hcit)
                    if hname is None:
                        return
                    hcontents = next(hcit)
                    nbytes = hnamebytes + len(hcontents)
                    yield (hname, hcontents, nbytes)
            except StopIteration:
                assert 0, "Bug: Unexpected end of lines in message."

        for hname, hcontents, bytes_used in HNameContentsGen(line_iter):
            message.addHeader(UnparsedHeader(astr(hname), hcontents))
            used_bytes += bytes_used

        # We haven't yet counted the eol eol at the end of the headers.
        used_bytes += 4
        clen = 0
        if hasattr(message, "content_lengthheader"):
            clen = message.content_lengthheader.number
        else:
            assert (message.viaheader.transport == SOCK_TYPE_IP_NAMES.UDP)

        log.debug("Expecting %d bytes of body", clen)
        if clen:
            if not hasattr(message, "content_typeheader"):
                raise ParseError(
                    "Message with non-empty body has no content type.")

        rest = string[used_bytes:]

        if len(rest) < clen:
            raise ParseError(
                "Body is shorter than specified: got %d expected %d" % (
                    len(rest), clen))

        if hasattr(message, "content_typeheader"):
            ctype = message.content_typeheader.content_type
            if ctype != sdpsyntax.SIPBodyType:
                raise ParseError("Unsupported Content-type: %r", ctype)
            message.addBody(Body(type=ctype, content=rest[:clen]))
            used_bytes += clen

        message.parsedBytes = used_bytes

        log.debug("Used %d of %d bytes", used_bytes, len(string))

        return message

    @classmethod
    def requestname(cls):
        if not cls.isrequest():
            raise AttributeError(
                "{cls.__name__!r} is not a request so has no request "
                "name.".format(**locals()))

        return cls.__name__.replace("Message", "")

    @classmethod
    def isrequest(cls):
        return not cls.isresponse()

    @classmethod
    def isresponse(cls):
        log.debug("Check if %r class is Response.", cls.__name__)
        return cls.__name__.find("Response") != -1

    @classmethod
    def HeaderAttrNameFromType(cls, htype):
        log.detail('Get header attribute name from type %r', htype)
        htype = getattr(Header.types, htype)
        return "%s%s" % (htype.replace("-", "_"), "Header")

    @classmethod
    def MakeStartline(cls):
        log.debug("Class %r has type %r", cls.__name__, cls.type)
        return getattr(Request, cls.type)()

    def __init__(self, autofillheaders=True, configure_bindings=True,
                 **kwargs):
        """Initialize a `Message`."""

        super(Message, self).__init__(**kwargs)

        if autofillheaders:
            self.autofillheaders()

        if configure_bindings:
            self.enableBindings()

    def enableBindings(self):
        fbs = getattr(self, 'field_bindings', None)
        if fbs is not None:
            log.debug("Configure %r bindings: %r", self.type, fbs)
            self.bindBindings(fbs)

    def addHeader(self, hdr):
        """Adds a header at the start of the first set of headers in the
        message, if headers of that type exist, else adds it to the end of the
        list of headers.

        E.g:
        Message: ToHeader, FromHeader, ViaHeader, ContactHeader
        addHeader(ViaHeader) ->
        Message: ToHeader, FromHeader, ViaHeader, ViaHeader, ContactHeader
        """
        htype = hdr.type
        clname = self.__class__.__name__
        log.debug("Add header %r instance type %r", clname, htype)
        new_headers = []

        log.detail("Old headers: %r", [_hdr.type for _hdr in self.headers])
        for oh in self.headers:
            if hdr is not None and htype == oh.type:
                # We've found the location for the new header to go in the list
                # (next to the first set of headers of the same type). However,
                # we can't set it now because this won't update the bindings.
                # Therefore add the existing first header again, then we can
                # set the new header via setattr() and it will correctly unbind
                # the old header and rebind the new one.
                new_headers.append(oh)
            new_headers.append(oh)

        log.detail(
            "Intermediate headers: %r", [_hdr.type for _hdr in new_headers])
        self.headers = new_headers

        hattr = self.HeaderAttrNameFromType(htype)
        log.debug("Set new header attr %r", hattr)
        setattr(self, hattr, hdr)
        log.debug(
            "Headers after add: %r", [_hdr.type for _hdr in self.headers])

    def autofillheaders(self):
        log.debug("Autofill %r headers", self.__class__.__name__)
        currentHeaderSet = set([_hdr.type for _hdr in self.headers])
        nhs = list(self.headers)
        for hdr in self.mandatoryheaders:
            if hdr not in currentHeaderSet:
                nh = getattr(Header, hdr)()
                nhs.append(nh)
        self.headers = nhs

        for mheader_name, mparams in iteritems(self.mandatoryparameters):
            mheader = getattr(self, self.HeaderAttrNameFromType(mheader_name))
            for param_name in mparams:
                setattr(
                    mheader.field.parameters, param_name,
                    getattr(Param, param_name)())

    def addBody(self, body):
        self.bodies = self.bodies + [body]

    #
    # =================== ATTRIBUTES ==========================================
    #
    def setBodies(self, bodies):
        log.debug("%r message set Bodies", self.__class__.__name__)
        log.detail("  bodies are: %r", bodies)
        existing_bodies = self._msg_bodies
        log.detail("  existing bodies are %r", existing_bodies)
        self._msg_bodies = bodies
        if len(bodies) == 0:
            if hasattr(self, "content_typeheader"):
                del self.content_typeheader
            return

        if len(bodies) > 1:
            raise ValueError("Currently multiple bodies are not supported.")

        if not hasattr(self, "content_lengthheader"):
            log.debug("Add content length header since we have bodies.")
            self.content_lengthheader = Header.content_length()

        if not hasattr(self, "content_typeheader"):
            log.debug("Add content type header")
            self.content_typeheader = Header.content_type()

        log.detail(
            "existing bodies before binding update: %r", existing_bodies)
        log.detail(
            "new bodies before binding update: %r", bodies)
        self.vb_updateAttributeBindings("bodies", existing_bodies, bodies)
        self.vb_updateAttributeBindings(
            "body",
            None if not existing_bodies else existing_bodies[0],
            None if not bodies else bodies[0])

    #
    # =================== INTERNAL METHODS ===================================
    #
    def bytesGen(self):

        log.debug(
            "%d headers, %d bodies.", len(self.headers), len(self.bodies))

        yield bytes(self.startline)
        eol = b'\r\n'
        yield eol
        for hdr in self.headers:
            for bs in hdr.safeBytesGen():
                yield bs
            yield eol
        yield eol

        bds = self.bodies
        assert len(bds) <= 1, "Only support one body currently."

        for body in bds:
            for bs in body.safeBytesGen():
                yield bs

    def __getattr__(self, attr):
        """Get some part of the message. E.g. get a particular header like:
        message.toheader
        """

        reqmo = self.reqattrre.match(attr)
        if reqmo is not None:
            sl = self.startline
            if sl.type == reqmo.group(1):
                return sl

        hmo = self.headerattrre.match(attr)
        if hmo is not None:
            canonicalheadername = util.sipheader(hmo.group(1))
            hdrs = self.headers
            for index, header in enumerate(hdrs):
                if header.type == canonicalheadername:
                    break
            else:
                header = None
            if header is not None:
                if isinstance(header, Header):
                    return header

                assert isinstance(header, UnparsedHeader)
                hclass = getattr(Header, header.type)
                newh = hclass.Parse(header.contents)
                hdrs[index] = newh
                return newh

        try:
            return getattr(super(Message, self), attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} instance has no attribute "
                "{attr!r}".format(**locals()))

    def __setattr__(self, attr, val):
        """If we're setting a header then figure out which and set it
        appropriately.
        """
        assert attr != "value"
        log.detail(
            "%r instance set attribute %r", self.__class__.__name__, attr)

        htype, hindex, hexist = self._msg_headerAttributeTypeIndexObject(attr)
        if htype is not None:
            log.debug("Setting header type %r", htype)
            if hindex is None:
                self.headers.append(val)
            else:
                self.headers[hindex] = val
            self.vb_updateAttributeBindings(htype, hexist, val)
            return

        super(Message, self).__setattr__(attr, val)

    def __delattr__(self, attr):
        log.debug("%r delete attribute %r", self.__class__.__name__, attr)
        htype, hindex, hexist = self._msg_headerAttributeTypeIndexObject(attr)
        if htype is not None:
            if hexist is None:
                raise AttributeError(
                    "%r instance has no attribute %r to delete" % (
                        self.__class__.__name__, attr))
            del self.headers[hindex]
            self.vb_updateAttributeBindings(htype, hexist, None)
            return

        return super(Message, self).__delattr__(attr)

    def __repr__(self):
        return (
            "{0.__class__.__name__}("
            "startline={0.startline!r}, headers={0.headers!r}, "
            "bodies={0.bodies!r})"
            "".format(self))

    #
    # =================== INTERNAL METHODS ====================================
    #
    def _msg_headerAttributeTypeIndexObject(self, attr):
        hmo = self.headerattrre.match(attr)
        if hmo is None:
            log.detail("Attr %r is not a header attr.", attr)
            return None, None, None

        htype = util.sipheader(hmo.group(1))
        log.debug("Set the %r of type %r", attr, htype)
        index = -1
        existing_val = None
        for hdr, index in zip(self.headers, range(len(self.headers))):
            if hdr.type == htype:
                log.debug("  Found existing one.")
                existing_val = hdr
                break
        else:
            log.debug("Didn't find existing one")
            index = None

        return self.HeaderAttrNameFromType(htype), index, existing_val


@add_metaclass(type)
class MessageResponse(Message):
    """ A response message.

    NB this overrides the metaclass of Message as we don't want to attempt to
    generate subclasses from our type, which we don't have."""

    field_bindings = [

    ]

    @property
    def type(self):
        return self.startline.code

    def __init__(self, code=None, **kwargs):

        if code is not None:
            sl = Response(code)
            kwargs["startline"] = sl
        if "autofillheaders" not in kwargs:
            kwargs["autofillheaders"] = False

        super(MessageResponse, self).__init__(**kwargs)


class InviteMessage(Message):
    """An INVITE."""

    field_bindings = [
        ("startline.uri", "ToHeader.field.uri"),
        ("startline.protocol", "ViaHeader.field.protocol"),
        ("startline", "ViaHeader.field.parameters.branch.startline"),
        ("FromHeader.field.value.uri.aor.username",
         "ContactHeader.field.value.uri.aor.username"),
        ("ContactHeader.host", "ViaHeader.host"),
        ("startline.type", "CSeqHeader.reqtype"),
    ]

    mandatoryheaders = [
        Header.types.To,
        Header.types.From,
        Header.types.Contact,
        Header.types.Via]

    mandatoryparameters = {
        Header.types.From: [Param.types.tag],
        Header.types.Via: [Param.types.branch]
    }


class ByeMessage(Message):
    """An BYE."""

    field_bindings = [
        ("startline.uri", "ToHeader.uri"),
        ("startline.protocol", "ViaHeader.protocol"),
        ("startline", "ViaHeader.field.parameters.branch.startline"),
        ("FromHeader.field.value.uri.aor.username",
         "ContactHeader.field.value.uri.aor.username"),
        ("ContactHeader.host", "ViaHeader.host"),
        ("startline.type", "CseqHeader.reqtype")]

    mandatoryheaders = [
        Header.types.Contact]

    mandatoryparameters = {
        Header.types.From: [Param.types.tag],
        Header.types.Via: [Param.types.branch]
    }


class AckMessage(Message):
    """An ACK."""

    field_bindings = [
        ("startline.uri", "ToHeader.field.uri"),
        ("startline.protocol", "ViaHeader.field.protocol"),
        ("startline", "ViaHeader.field.parameters.branch.startline"),
        ("FromHeader.field.value.uri.aor.username",
         "ContactHeader.field.value.uri.aor.username"),
        ("ContactHeader.field.value.uri.aor.host",
         "ViaHeader.field.host.host"),
        ("startline.type", "CseqHeader.field.reqtype"),
    ]

Message.addSubclassesFromDict(locals())
