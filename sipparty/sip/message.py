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
import six
import re
import logging
import collections

from sipparty import (util, vb, parse)
import prot
from prot import Incomplete
import components
import param
from param import Param
from request import Request
from response import Response
from header import Header

log = logging.getLogger(__name__)
bytes = six.binary_type


@six.add_metaclass(
    # The FSM type needs both the attributesubclassgen and the cumulative
    # properties metaclasses.
    type('Message',
         (util.CCPropsFor(("mandatoryheaders", "mandatoryparameters")),
          util.attributesubclassgen,),
         dict()))
@util.TwoCompatibleThree
class Message(vb.ValueBinder):
    """Generic message class. Use `Request` or `Response` rather than using
    this directly.
    """

    types = Request.types

    mandatoryheaders = [
        Header.types.From,  Header.types.To, Header.types.Via,
        Header.types.call_id, Header.types.cseq, Header.types.max_forwards]
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

    bindings = []

    reqattrre = re.compile(
        "(%s)request" % (types.REPattern(),), flags=re.IGNORECASE)

    headerattrre = re.compile(
        "(%s)Header" % Header.types.REPattern().replace(
            "-", "[-_]"), flags=re.IGNORECASE)
    type = util.ClassType("Message")

    MethodRE = re.compile("{Method}".format(**prot.__dict__))
    ResponseRE = re.compile("{SIP_Version}".format(**prot.__dict__))
    HeaderSeparatorRE = re.compile(
        "{CRLF}(?:({token}){COLON}|{CRLF})".format(**prot.__dict__))

    @classmethod
    def Parse(cls, string):

        lines = cls.HeaderSeparatorRE.split(string)
        log.detail("Header split: %r", lines)

        startline = lines[0]

        if cls.ResponseRE.match(startline):
            log.debug("Attempt Message Parse of %r as a response.", startline)
            reqline = Response.Parse(startline)
            log.debug(reqline)
            message = MessageResponse(startline=reqline)
            log.debug("Success. Type: %r.", message.type)

        elif cls.MethodRE.match(startline):
            log.debug("Attempt Message Parse of request %r.", startline)
            requestline = Request.Parse(startline)
            message = getattr(Message, requestline.type)(
                startline=requestline, autofillheaders=False)
            log.debug("Message is of type %r", message.type)
        else:
            raise parse.ParseError(
                "Startline is not a SIP startline: %r." % (startline,))

        body_lines = lines[1:]

        def HNameContentsGen(hclist):
            hcit = iter(hclist)
            try:
                while True:
                    hname = hcit.next()
                    body_lines.pop(0)
                    if hname is None:
                        return
                    hcontents = hcit.next()
                    body_lines.pop(0)
                    yield (hname, hcontents)
            except StopIteration:
                assert 0, "Bug: Unexpected end of lines in message."

        for hname, hcontents in HNameContentsGen(lines[1:]):
            log.debug("Add header %r", hname)
            log.detail("Contents: %r", hcontents)
            newh = getattr(Header, hname).Parse(hcontents)
            log.detail("Header parsed as: %r", newh)
            message.addHeader(newh)

        log.debug("SDP lines %r", body_lines)

        return message

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
        log.debug("Check if %r class is Response.", cls.__name__)
        return cls.__name__.find("Response") != -1

    @classmethod
    def HeaderAttrNameFromType(cls, htype):
        return "%s%s" % (getattr(Header.types, htype), "Header")

    def __init__(self, startline=None, headers=None, bodies=None,
                 autofillheaders=True, configure_bindings=True):
        """Initialize a `Message`."""

        super(Message, self).__init__()

        for field in ("headers", "bodies"):
            if locals()[field] is None:
                setattr(self, field, [])
            else:
                setattr(self, field, locals()[field])

        if startline is None:
            try:
                ty = self.type
                log.debug("Make new startline of type %r.", self.type)
                startline = getattr(Request, self.type)()
            except Exception:
                raise
        self.startline = startline

        if autofillheaders:
            self.autofillheaders()

        if configure_bindings and hasattr(self, "field_bindings"):
            log.debug(
                "Configure %r bindings: %r", self.type, self.field_bindings)
            self.bindBindings(self.field_bindings)

    def addHeader(self, hdr):
        """Adds a header at the start of the first set of headers in the
        message, if headers of that type exist, else adds it to the end of the
        list of headers.

        E.g:
        Message: ToHeader, FromHeader, ViaHeader, ContactHeader
        addHeader(ViaHeader) ->
        Message: ToHeader, FromHeader, ViaHeader, ViaHeader, ContactHeader
        """
        assert hdr is not None
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
        for hdr in self.mandatoryheaders:
            if hdr not in currentHeaderSet:
                self.addHeader(getattr(Header, hdr)())

        for mheader_name, mparams in six.iteritems(self.mandatoryparameters):
            mheader = getattr(self, self.HeaderAttrNameFromType(mheader_name))
            for param_name in mparams:
                setattr(
                    mheader.field.parameters, param_name,
                    getattr(Param, param_name)())

    #
    # =================== INTERNAL METHODS ===================================
    #
    def __bytes__(self):

        log.debug(
            "%d headers, %d bodies.", len(self.headers), len(self.bodies))

        components = [self.startline]
        components.extend(self.headers)
        # Note we need an extra newline between headers and bodies
        components.append(b"")
        if self.bodies:
            components.extend(self.bodies)
            components.append(b"")

        components.append(b"")  # need a newline at the end.

        log.debug("Last line: %r", components[-1])
        try:
            rp = prot.EOL.join([bytes(_cp) for _cp in components])
            return rp
        except Incomplete as exc:
            exc.args += ('Message type %r' % self.type,)
            raise

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
            canonicalheadername = util.sipheader(hmo.group(1))
            for header in self.headers:
                if header.type == canonicalheadername:
                    return header

        try:
            return getattr(super(Message, self), attr)
        except AttributeError:
            raise AttributeError(
                "{self.__class__.__name__!r} object has no attribute "
                "{attr!r}".format(**locals()))

    def __setattr__(self, attr, val):
        """If we're setting a header then figure out which and set it
        appropriately.
        """
        assert attr != "value"
        hmo = self.headerattrre.match(attr)
        log.detail(
            "%r instance set attribute %r", self.__class__.__name__, attr)
        if hmo is not None:
            htype = util.sipheader(hmo.group(1))
            log.debug("Set the %r of type %r", attr, htype)
            index = -1
            existing_val = None
            for hdr, index in zip(self.headers, range(len(self.headers))):
                if hdr.type == htype:
                    log.debug("  Found existing one.")
                    existing_val = hdr
                    self.headers[index] = val
                    break
            else:
                log.debug("Didn't find existing one")
                self.headers.append(val)
                index += 1
            # Update bindings following change.
            self.vb_updateAttributeBindings(attr, existing_val, val)
            return

        super(Message, self).__setattr__(attr, val)

    def __repr__(self):
        return (
            "{0.__class__.__name__}("
            "startline={0.startline!r}, headers={0.headers!r}, "
            "bodies={0.bodies!r})"
            "".format(self))


@six.add_metaclass(type)
class MessageResponse(Message):
    """ A response message.

    NB this overrides the metaclass of Message as we don't want to attempt to
    generate subclasses from our type, which we don't have."""

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
        ("ContactHeader.field.value.uri.aor.host",
         "ViaHeader.field.host.host"),
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
        ("startline.type", "CseqHeader.field.reqtype")]

Message.addSubclassesFromDict(locals())
