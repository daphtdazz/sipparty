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

from sipparty import (util, vb, parse)
import prot
import components
import param
import transform
from param import Param
import request
import response
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

    types = request.Request.types

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
        "(%s)Header" % "|".join(map(
            util.attributesubclassgen.NormalizeGeneratingAttributeName,
            Header.types)), flags=re.IGNORECASE)
    type = util.ClassType("Message")

    @classmethod
    def Parse(cls, string):

        # This could be optimised using a generator taking slices of the
        # string: stackoverflow.com/questions/3054604/iterate-over-the-lines-
        # of-a-string
        lines = string.split(prot.EOL)

        # Restitch lines if any start with SP (space) or HT (horizontal tab).
        joined_lines = []
        curr_lines = []
        for line in lines:
            if len(line) > 0 and line[0] in (' ', '\t'):
                curr_lines.append(line.lstrip())
                continue
            if len(curr_lines) > 0:
                joined_lines.append("".join(curr_lines))
                del curr_lines[:]
            curr_lines.append(line)
        else:
            if len(curr_lines) > 0:
                joined_lines.append("".join(curr_lines))

        lines = joined_lines
        log.debug("Sectioned lines: {0!r}".format(lines))
        startline = lines.pop(0)

        # Fix the startline and build the message.
        try:
            # !!! TODO: This is highly suboptimal; must come back and fix the
            # parsing so that requests and responses are parsed more
            # equivocally.
            log.debug("Attempt Message Parse of %r as a request.", startline)
            requestline = request.Request.Parse(startline)
            message = getattr(Message, requestline.type)(
                startline=requestline, autofillheaders=False)
            log.debug("Message is of type %r", message.type)
        except parse.ParseError:
            # Try response...
            log.debug("Attempt Message Parse of %r as a response.", startline)
            reqline = response.Response.Parse(startline)
            log.debug(reqline)
            message = Response(startline=reqline)
            log.debug("Success. Type: %r.", message.type)

        for line, ln in zip(lines, range(1, len(lines) + 1)):
            if len(line) == 0:
                break
            message.addHeader(Header.Parse(line))
        body_lines = lines[ln:]
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
        return cls.__name__.find("Response") != -1

    def __init__(self, startline=None, headers=None, bodies=None,
                 autofillheaders=True):
        """Initialize a `Message`."""

        super(Message, self).__init__()

        if startline is None:
            try:
                ty = self.type
                log.debug("Make new startline of type %r.", self.type)
                startline = getattr(request.Request, self.type)()
            except Exception:
                raise
        self.startline = startline

        for field in ("headers", "bodies"):
            if locals()[field] is None:
                setattr(self, field, [])
            else:
                setattr(self, field, locals()[field])

        if autofillheaders:
            self.autofillheaders()
        self._establishbindings()

    def addHeader(self, hdr):
        new_headers = []
        for oh in self.headers:
            if hdr is not None and hdr.type == oh.type:
                new_headers.append(hdr)
                hdr = None
            new_headers.append(oh)
        if hdr is not None:
            new_headers.append(hdr)
        self.headers = new_headers

    def autofillheaders(self):
        for hdr in self.mandatoryheaders:
            if hdr not in [_hdr.type for _hdr in self.headers]:
                self.addHeader(getattr(Header, hdr)())

        for mheader_name, mparams in six.iteritems(self.mandatoryparameters):
            mheader = getattr(self, mheader_name + "Header")
            for param_name in mparams:
                setattr(
                    mheader.field.parameters, param_name,
                    getattr(Param, param_name)())

    def applyTransform(self, targetmsg, tform):
        copylist = tform[transform.KeyActCopy]

        def setattratpath(obj, path, val):
            nextobj = obj
            tocomponents = path.split(".")
            for to in tocomponents[:-1]:
                nextobj = getattr(nextobj, to)
            to_target = nextobj

            setattr(to_target, tocomponents[-1], val)

        for copy_tuple in copylist:
            frmattr = copy_tuple[0]
            if len(copy_tuple) > 1:
                toattr = copy_tuple[1]
            else:
                toattr = frmattr
            log.debug("Copy %r to %r", frmattr, toattr)

            nextobj = self
            for fm in frmattr.split("."):
                nextobj = getattr(nextobj, fm)
            from_attribute = nextobj

            setattratpath(targetmsg, toattr, from_attribute)

        addlist = tform.get(transform.KeyActAdd, [])
        for add_tuple in addlist:
            tpath = add_tuple[0]
            new_obj = add_tuple[1]()
            log.debug("Adding %r at path %r", new_obj, tpath)
            setattratpath(targetmsg, tpath, new_obj)

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
        return prot.EOL.join([bytes(_cp) for _cp in components])

    def __getattr__(self, attr):
        """Get some part of the message. E.g. get a particular header like:
        message.toheader
        """

        reqmo = self.reqattrre.match(attr)
        if reqmo is not None:
            if self.startline.type == mo.group(1):
                return self.startline

        if attr in Header.types:
            canonicalheadername = util.sipheader(attr)
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
        if hmo is not None:
            htype = (
                util.attributesubclassgen
                .NormalizeGeneratingAttributeName(attr.replace("Header", '')))
            log.debug("Set the %r of type %r", attr, htype)
            index = -1
            for hdr, index in zip(self.headers, range(len(self.headers))):
                if hdr.type == htype:
                    log.debug("  Found existing one.")
                    self.headers[index] = val
                    break
            else:
                log.debug("Didn't find existing one")
                self.headers.append(val)
                index += 1

            return

        super(Message, self).__setattr__(attr, val)

    def __del__(self):
        log.debug("Deleting %r instance.", self.__class__.__name__)

    def _establishbindings(self):
        for binding in self.bindings:
            if len(binding) > 2:
                transformer = binding[2]
            else:
                transformer = None
            self.bind(binding[0], binding[1], transformer)


@six.add_metaclass(type)
class Response(Message):
    """ A response message.

    NB this overrides the metaclass of Message as we don't want to attempt to
    generate subclasses from our type, which we don't have."""

    @property
    def type(self):
        return self.startline.code

    def __init__(self, code=None, **kwargs):

        if code is not None:
            sl = response.Response(code)
            kwargs["startline"] = sl
        if "autofillheaders" not in kwargs:
            kwargs["autofillheaders"] = False

        super(Response, self).__init__(**kwargs)


class InviteMessage(Message):
    """An INVITE."""

    bindings = [
        ("startline.uri", "ToHeader.field.uri"),
        ("startline.protocol", "ViaHeader.field.protocol"),
        ("startline", "ViaHeader.field.parameters.branch.startline"),
        ("FromHeader.field.value.uri.aor.username",
         "ContactHeader.field.value.uri.aor.username"),
        ("ContactHeader.field.value.uri.aor.host",
         "ViaHeader.field.host.host"),
        ("startline.type", "CseqHeader.field.reqtype")]

    mandatoryheaders = [
        Header.types.Contact]

    mandatoryparameters = {
        Header.types.From: [Param.types.tag],
        Header.types.Via: [Param.types.branch]
    }


class ByeMessage(Message):
    """An BYE."""

    bindings = [
        ("startline.uri", "ToHeader.field.uri"),
        ("startline.protocol", "ViaHeader.field.protocol"),
        ("startline", "ViaHeader.field.parameters.branch.startline"),
        ("FromHeader.field.value.uri.aor.username",
         "ContactHeader.field.value.uri.aor.username"),
        ("ContactHeader.field.value.uri.aor.host",
         "ViaHeader.field.host.host"),
        ("startline.type", "CseqHeader.field.reqtype")]

    mandatoryheaders = [
        Header.types.Contact]

    mandatoryparameters = {
        Header.types.From: [Param.types.tag],
        Header.types.Via: [Param.types.branch]
    }

Message.addSubclassesFromDict(locals())
