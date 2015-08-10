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
import socket
import logging
import prot
from six import binary_type as bytes
from sipparty import (vb, Parser, ParsedProperty, ParsedPropertyOfClass)
from sipparty.util import TwoCompatibleThree, TupleRepresentable
from sipparty.deepclass import (DeepClass, dck)
import defaults

log = logging.getLogger(__name__)


@TwoCompatibleThree
class Host(Parser, TupleRepresentable, vb.ValueBinder):

    parseinfo = {
        Parser.Pattern:
            # Have to expand {host} because it uses {IPv6reference} instead of
            # {IPv6address}.
            "(?:[[]({IPv6address})[]]|({IPv4address})|({hostname}))"
            "(?:{COLON}({port}))?$"
            "".format(**prot.__dict__),
        Parser.Mappings:
            [("address",),
             ("address",),
             ("address",),
             ("port", int)],
    }

    def __init__(self, address=None, port=None, **kwargs):
        super(Host, self).__init__()
        self.address = address
        self.port = port

    def addrTuple(self):
        addrHost = "" if self.address is None else self.address
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
            log.detail("Resolve address: %s", bytes(address))
            try:
                ais = socket.getaddrinfo(bytes(address), 0)
                for ai in ais:
                    if ai[0] == socket.AF_INET:
                        break
                    isIpv6 = True
            except socket.gaierror:
                pass

        if address and port:
            if isIpv6:
                return b"[{address}]:{port}".format(**locals())
            return b"{address}:{port}".format(**locals())

        if self.address:
            if isIpv6:
                return b"[{address}]".format(**locals())
            return b"{address}".format(**locals())

        return b""

    def tupleRepr(self):
        return (self.address, self.port)


@TwoCompatibleThree
class AOR(
        DeepClass("_aor_", {
            "username": {},
            "host": {
                dck.descriptor: ParsedPropertyOfClass(Host), dck.gen: Host}}),
        Parser, TupleRepresentable, vb.ValueBinder):
    """A AOR object."""

    parseinfo = {
        Parser.Pattern:
            b"(?:({user}|{telephone_subscriber})(?::{password})?@)?"
            "({hostport})".format(**prot.__dict__),
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
        super(AOR, self).__init__()
        self.username = username
        if host is None:
            host = Host()
        self.host = host

    #
    # =================== MAGIC METHODS =======================================
    #
    def __bytes__(self):

        host = self.host
        if not host:
            raise prot.Incomplete("AOR %r does not have a host." % self)

        uname = self.username
        if uname:
            return b"{0}@{1}".format(uname, host)

        return bytes(host)

    def tupleRepr(self):
        return (self.username, self.host)


@TwoCompatibleThree
class URI(
        DeepClass("_uri_", {
            "scheme": {dck.gen: lambda: defaults.scheme},
            "aor": {dck.descriptor: ParsedPropertyOfClass(AOR), dck.gen: AOR},
            "parameters": {dck.gen: lambda: b""},
            "headers": {dck.gen: lambda: b""},
            "absoluteURIPart": {dck.gen: lambda: None}}),
        Parser, vb.ValueBinder):
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
            "(?:"
            "(sips?):"  # Most likely sip or sips uri.
            "((?:{userinfo})?{hostport})"
            "({uri_parameters})({headers})?|"
            "({scheme}):"  # Else some other scheme.
            "({hier_part}|{opaque_part})"
            ")".format(**prot.__dict__),
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

    def __init__(self, **kwargs):
        super(URI, self).__init__(**kwargs)

        # If it wasn't a SIP/SIPS URL, this contains the body of the URL (the
        # bit after the scheme).

    def __bytes__(self):
        if not self.scheme:
            raise prot.Incomplete("URI %r does not have a scheme." % self)

        if self.absoluteURIPart:
            auripart = bytes(self.absoluteURIPart)
            if not auripart:
                raise prot.Incomplete(
                    "URI %r has an empty absoluteURIPart" % self)
            return b"{0.scheme}:{0.absoluteURIPart}".format(self)

        aorbytes = bytes(self.aor)
        if not aorbytes:
            raise prot.Incomplete(
                "URI %r has an empty aor." % self)
        return "{0.scheme}:{0.aor}{0.parameters}{0.headers}".format(self)


@TwoCompatibleThree
class DNameURI(
        DeepClass("_dnur_", {
            "uri": {dck.descriptor: ParsedPropertyOfClass(URI), dck.gen: URI},
            "display_name": {dck.gen: lambda: b""},
            "headers": {dck.gen: lambda: b""},
            "absoluteURIPart": {dck.gen: lambda: None}}),
        Parser, vb.ValueBinder):
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
        ("uri", ["aor", "host"])]

    display_name_mapping = ("display_name", None, lambda x: x.strip())
    uri_mapping = ("uri", URI)
    parseinfo = {
        Parser.Pattern:
            b"(?:{LAQUOT}({addr_spec}){RAQUOT}|"
            "({addr_spec})|"
            "({display_name}){LAQUOT}({addr_spec}){RAQUOT})"
            "".format(**prot.__dict__),
        Parser.Mappings:
            [uri_mapping,
             uri_mapping,
             display_name_mapping,
             uri_mapping]
    }

    def __init__(self, **kwargs):
        super(DNameURI, self).__init__(**kwargs)

    def __bytes__(self):
        if self.display_name and self.uri:
            return(b"\"{self.display_name}\" <{self.uri}>".format(**locals()))

        if self.uri:
            return(b"<{self.uri}>".format(**locals()))

        raise prot.Incomplete(
            "DNameURI %r needs at least a URI to mean something." % self)
