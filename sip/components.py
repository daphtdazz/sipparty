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
import _util
import vb
from parse import Parser

bytes = six.binary_type


@_util.TwoCompatibleThree
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


@_util.TwoCompatibleThree
class AOR(Parser, vb.ValueBinder):
    """A AOR object."""

    parseinfo = {
        Parser.Pattern:
            "(.*)"
            "@"
            "(.*)$",
        Parser.Mappings:
            [("username",),
             ("host", Host)],
    }

    def __init__(self, username=None, host=None, **kwargs):
        super(AOR, self).__init__()
        self.username = username
        self.host = (
            host
            if host is not None and not isinstance(host, str) else
            Host(host=host, **kwargs))

    def __bytes__(self):
        if self.username and self.host:
            return b"{username}@{host}".format(**self.__dict__)

        if self.host:
            return b"{host}".format(**self.__dict__)

        return b""

    def __repr__(self):
        return (
            "{self.__class__.__name__}(username={self.username!r}, "
            "host={self.host!r})"
            "".format(self=self))


@_util.TwoCompatibleThree
class URI(Parser, vb.ValueBinder):
    """A URI object."""

    parseinfo = {
        Parser.Pattern:
            "(sip|sips)"
            ":"
            "(.*)$",
        Parser.Mappings:
            [("scheme",),
             ("aor", AOR)],
    }

    def __init__(self, scheme=None, aor=None):
        super(URI, self).__init__()

        if scheme is None:
            scheme = defaults.scheme
        if aor is None:
            aor = AOR()

        for prop in dict(locals()):
            if prop == "self":
                continue
            setattr(self, prop, locals()[prop])

    def __bytes__(self):
        return "{scheme}:{aor}".format(**self.__dict__)


@_util.TwoCompatibleThree
class DNameURI(Parser, vb.ValueBinder):
    """A display name plus a uri value object.

    This is basically (name-addr/addr-spec) where:

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

    delegateattributes = ["dname", "uri"]

    dname_mapping = ("dname", None, lambda x: x.strip())
    uri_mapping = ("uri", URI)
    parseinfo = {
        Parser.Pattern:
            "("  # Either we want...
            "([^<]+)"  # something which is not in angle brackets (disp. name)
            "<([^>]+)>|"  # followed by a uri that is in <> OR...
            "("
            "(\w.*)\s+|"  # optionally at least one non-space for the disp
            "\s*"  # or just spaces
            ")"
            "([^\s]+)"  # at least one thing that isn't a space for the uri
            "\s*"  # followed by arbitrary space
            ")$",
        Parser.Mappings:
            [None,
             dname_mapping,
             uri_mapping,
             None,
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

        return b""

import defaults
