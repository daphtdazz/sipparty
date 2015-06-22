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
# We import defaults at the bottom, since defaults uses these classes, and so
# they must always be declared before defaults is.
# import defaults
import six

import prot
from sipparty import (util, vb, Parser, ParsedProperty)

bytes = six.binary_type


@util.TwoCompatibleThree
class Host(Parser, vb.ValueBinder):

    parseinfo = {
        Parser.Pattern:
            "({host})(?:{COLON}({port}))?$"
            "".format(**prot.__dict__),
        Parser.Mappings:
            [("host",),
             ("port",)],
    }

    def __init__(self, host=None, port=None):
        super(Host, self).__init__()
        self.host = host
        self.port = port

    def addrTuple(self):
        addrHost = "" if self.host is None else self.host
        addrPort = defaults.port if self.port is None else self.port
        addrFlowInfo = 0
        addrScopeID = 0
        return (addrHost, addrPort, addrFlowInfo, addrScopeID)

    def __bytes__(self):

        host = self.host
        port = self.port

        if not port and hasattr(defaults, "useports") and defaults.useports:
            port = defaults.port

        if host and port:
            return b"{host}:{port}".format(**locals())

        if self.host:
            return b"{host}".format(**locals())

        return b""

    def __repr__(self):
        return b"Host(host={host}, port={port})".format(**self.__dict__)

    def __eq__(self, other):
        return (
            self.host == other.host and self.port == other.port)


@util.TwoCompatibleThree
class AOR(Parser, vb.ValueBinder):
    """A AOR object."""

    parseinfo = {
        Parser.Pattern:
            b"(?:({user}|{telephone_subscriber})(?::{password})?@)?"
            "({hostport})".format(**prot.__dict__),
        Parser.Mappings:
            [("username",),
             ("host", Host)],
    }

    host = ParsedProperty("_aor_host", Host)

    def __init__(self, username=None, host=None, **kwargs):
        super(AOR, self).__init__()
        self._aor_host = None
        self.username = username
        if host is None:
            host = Host()
        self.host = host

    def __bytes__(self):

        host = self.host
        if not host:
            raise prot.Incomplete("AOR %r does not have a host." % self)

        uname = self.username
        if uname:
            return b"{0}@{1}".format(uname, host)

        return bytes(host)

    def __repr__(self):
        return (
            "{0.__class__.__name__}(username={0.username!r}, "
            "host={0.host!r})"
            "".format(self))

    def __eq__(self, other):
        return (
            other.username == self.username and
            other.host == self.host)


@util.TwoCompatibleThree
class URI(Parser, vb.ValueBinder):
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

    def __init__(
            self, scheme=None, aor=None, absoluteURIPart=None, parameters=b"",
            headers=b""):
        super(URI, self).__init__()

        if scheme is None:
            scheme = defaults.scheme
        self.scheme = scheme

        if aor is None:
            aor = AOR()
        self.aor = aor

        # If it wasn't a SIP/SIPS URL, this contains the body of the URL (the
        # bit after the scheme).
        self.absoluteURIPart = absoluteURIPart

        self.parameters = parameters
        self.headers = headers

    def __bytes__(self):
        if not self.scheme:
            raise prot.Incomplete("URI %r does not have a scheme." % self)

        if self.absoluteURIPart:
            auripart = bytes(self.absoluteURIPart)
            if not auripart:
                raise prot.Incomplete(
                    "URI %r has an empty absoluteURIPart" % self)
            return b"{scheme}:{absoluteURIPart}".format(**self.__dict__)

        aorbytes = bytes(self.aor)
        if not aorbytes:
            raise prot.Incomplete(
                "URI %r has an empty aor." % self)
        return "{scheme}:{aor}{parameters}{headers}".format(**self.__dict__)

    def __repr__(self):
        return (
            "{0.__class__.__name__}(scheme={0.scheme!r}, aor={0.aor!r}, "
            "absoluteURIPart={0.absoluteURIPart!r}, "
            "parameters={0.parameters!r}, headers={0.headers!r})"
            "".format(self))


@util.TwoCompatibleThree
class DNameURI(Parser, vb.ValueBinder):
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

    delegateattributes = ["dname", "uri"]

    dname_mapping = ("dname", None, lambda x: x.strip())
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
             dname_mapping,
             uri_mapping]
    }

    def __init__(self, dname=None, uri=None):
        super(DNameURI, self).__init__()

        if uri is None:
            uri = URI()

        self.dname = dname
        self.uri = uri

    def __bytes__(self):
        if self.dname and self.uri:
            return(b"\"{self.dname}\" <{self.uri}>".format(**locals()))

        if self.uri:
            return(bytes(self.uri))

        raise prot.Incomplete(
            "DNameURI %r needs at least a URI to mean something." % self)

    def __repr__(self):
        return (
            "{0.__class__.__name__}(dname={0.dname!r}, uri={0.uri!r})"
            "".format(self))

import defaults
