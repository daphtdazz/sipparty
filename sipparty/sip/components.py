"""components.py

Components of data that make up SIP messages.

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
import logging
from numbers import Integral
from six import binary_type as bytes
from socket import AF_INET6
from . import defaults
from .prot import (bdict as abnf_name_bdict, Incomplete)
from ..classmaker import classbuilder
from ..deepclass import (DeepClass, dck)
from ..parse import (Parser, ParsedProperty, ParsedPropertyOfClass)
from ..transport import IPAddressFamilyFromName
from ..util import (astr, TwoCompatibleThree, TupleRepresentable)
from ..vb import ValueBinder

log = logging.getLogger(__name__)


@TwoCompatibleThree
@classbuilder(
    bases=(
        DeepClass("_hst_", {
            "address": {dck.check: lambda x: isinstance(x, bytes)},
            "port": {
                dck.check: (
                    lambda x: isinstance(x, Integral) and 0 <= x <= 0xffff),
            }
        }),
        Parser, TupleRepresentable, ValueBinder
    )
)
class Host:
    parseinfo = {
        Parser.Pattern:
            # Have to expand 'host' because it uses 'IPv6reference' instead of
            # 'IPv6address'.
            b"(?:[[](%(IPv6address)s)[]]|(%(IPv4address)s)|(%(hostname)s))"
            b"(?:%(COLON)s(%(port)s))?$"
            b"" % abnf_name_bdict,
        Parser.Mappings:
            [("address",),
             ("address",),
             ("address",),
             ("port", int)],
    }

    def addrTuple(self):
        addrHost = '' if self.address is None else astr(self.address)
        addrPort = defaults.port if self.port is None else self.port
        addrFlowInfo = 0
        addrScopeID = 0
        return (addrHost, addrPort, addrFlowInfo, addrScopeID)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __bytes__(self):

        address = self.address
        port = self.port

        if not port and hasattr(defaults, "useports") and defaults.useports:
            port = defaults.port

        isIpv6 = False
        if address:
            log.detail("Resolve address: %r", address)

            isIpv6 = IPAddressFamilyFromName(address) == AF_INET6

        if address and port:
            if isIpv6:
                return b"[%s]:%d" % (address, port)
            return b"%s:%d" % (address, port)

        if self.address:
            if isIpv6:
                return b"[%s]" % address
            return b"%s" % self.address

        return b""

    def tupleRepr(self):
        return (self.address, self.port)


@TwoCompatibleThree
@classbuilder(
    bases=(
        DeepClass("_aor_", {
            "username": {dck.check: lambda x: isinstance(x, bytes)},
            "host": {
                dck.descriptor: ParsedPropertyOfClass(Host), dck.gen: Host}}),
        Parser, TupleRepresentable, ValueBinder
    )
)
class AOR:
    """A AOR object."""

    parseinfo = {
        Parser.Pattern:
            b"(?:(%(user)s|%(telephone_subscriber)s)(?::%(password)s)?@)?"
            b"(%(hostport)s)" % abnf_name_bdict,
        Parser.Mappings:
            [("username",),
             ("host", Host)],
    }

    vb_dependencies = [
        ["host", ["address", "port"]]]

    @classmethod
    def ExtractAOR(cls, target):
        if hasattr(target, "aor"):
            return target.aor

        if isinstance(target, AOR):
            return target

        if isinstance(target, bytes):
            return cls.Parse(target)

        raise TypeError(
            "%r instance cannot be derived from %r instance." % (
                AOR.__class__.__name__, target.__class__.__name__))

    host = ParsedProperty("_aor_host", Host)

    def __init__(self, username=None, host=None, **kwargs):
        super(AOR, self).__init__(username=username, host=host, **kwargs)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __bytes__(self):

        host = self.host
        if host is None:
            raise Incomplete("AOR %r does not have a host" % self)

        host_bytes = bytes(host)
        if len(host_bytes) == 0:
            raise Incomplete("AOR %r has a zero-length host" % self)

        uname = self.username
        if uname:
            return b"%s@%s" % (uname, host_bytes)

        return host_bytes

    def tupleRepr(self):
        return (self.username, self.host)


@TwoCompatibleThree
@classbuilder(
    bases=(
        DeepClass("_uri_", {
            "scheme": {dck.gen: lambda: defaults.scheme},
            "aor": {dck.descriptor: ParsedPropertyOfClass(AOR), dck.gen: AOR},
            "parameters": {dck.gen: lambda: b''},
            "headers": {dck.gen: lambda: b''},
            "absoluteURIPart": {dck.gen: lambda: None}}),
        Parser, ValueBinder
    )
)
class URI:
    """A URI object.

    This decomposes addr-spec from RFC 3261:

    addr-spec      =  SIP-URI / SIPS-URI / absoluteURI
    SIP-URI          =  "sip:" [ userinfo ] hostport
                    uri-parameters [ headers ]
    SIPS-URI         =  "sips:" [ userinfo ] hostport
                        uri-parameters [ headers ]
    absoluteURI    =  scheme ":" ( hier-part / opaque-part )
    hier-part      =  ( net-path / abs-path ) [ "?" query ]
    net-path       =  "//" authority [ abs-path ]
    opaque-part    =  uric-no-slash *uric
    """

    parseinfo = {
        Parser.Pattern:
            b"(?:"
            b"(sips?):"  # Most likely sip or sips uri.
            b"((?:%(userinfo)s)?%(hostport)s)"
            b"(%(uri_parameters)s)(%(headers)s)?|"
            b"(%(scheme)s):"  # Else some other scheme.
            b"(%(hier_part)s|%(opaque_part)s)"
            b")" % abnf_name_bdict,
        Parser.Mappings:
            [("scheme",),
             ("aor", AOR),
             ("parameters",),
             ("headers",),
             ("scheme",),
             ("absoluteURIPart",)],
    }

    vb_dependencies = [
        ["aor", ["address", "port", "username", "host"]]]

    significant_attributes = ('scheme', 'aor', 'parameters', 'headers')

    def __init__(self, **kwargs):
        super(URI, self).__init__(**kwargs)

        # If it wasn't a SIP/SIPS URL, this contains the body of the URL (the
        # bit after the scheme).

    #
    # =================== MAGIC METHODS =======================================
    #
    def __bytes__(self):
        if not self.scheme:
            raise Incomplete("URI %r does not have a scheme." % self)

        if self.absoluteURIPart:
            auripart = bytes(self.absoluteURIPart)
            if not auripart:
                raise Incomplete("URI %r has an empty absoluteURIPart" % self)
            return b"%s:%s" % (self.scheme, self.absoluteURIPart)

        aorbytes = bytes(self.aor)
        if not aorbytes:
            raise Incomplete("URI %r has an empty aor." % self)
        return b'%s:%s%s%s' % (
            self.scheme, aorbytes, self.parameters, self.headers)

    def __eq__(self, other):

        return all([
            hasattr(other, component) and
            getattr(self, component) == getattr(other, component)
            for component in self.significant_attributes
        ])

    def __hash__(self):
        return hash(
            tuple(getattr(self, attr) for attr in self.significant_attributes))


@TwoCompatibleThree
@classbuilder(
    bases=(
        DeepClass("_dnur_", {
            "uri": {dck.descriptor: ParsedPropertyOfClass(URI), dck.gen: URI},
            "display_name": {dck.gen: lambda: b""},
            "headers": {dck.gen: lambda: b""},
            "absoluteURIPart": {dck.gen: lambda: None}}),
        Parser, ValueBinder
    )
)
class DNameURI:
    """A display name plus a uri value object.

    This is basically (name-addr/addr-spec) where:

    name-addr      =  [ display-name ] LAQUOT addr-spec RAQUOT
    display-name   =  *(token LWS)/ quoted-string

    contact-params     =  c-p-q / c-p-expires
                          / contact-extension
    c-p-q              =  "q" EQUAL qvalue
    c-p-expires        =  "expires" EQUAL delta-seconds
    contact-extension  =  generic-param
    delta-seconds      =  1*DIGIT

    """

    vb_dependencies = [
        ("uri", ("aor", "username", "host", "address", "port"))]

    display_name_mapping = ("display_name", lambda x: x.strip())
    uri_mapping = ("uri", URI)
    parseinfo = {
        Parser.Pattern:
            b"(?:%(LAQUOT)s(%(addr_spec)s)%(RAQUOT)s|"
            b"(%(addr_spec)s)|"
            b"(%(display_name)s)%(LAQUOT)s(%(addr_spec)s)%(RAQUOT)s)"
            b"" % abnf_name_bdict,
        Parser.Mappings:
            [uri_mapping,
             uri_mapping,
             display_name_mapping,
             uri_mapping]
    }

    def __bytes__(self):
        if self.display_name and self.uri:
            return(b"\"%s\" <%s>" % (self.display_name, self.uri))

        if self.uri:
            return(b"<%s>" % self.uri)

        raise Incomplete(
            "DNameURI %r needs at least a URI to mean something." % self)
