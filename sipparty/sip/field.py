"""field.py

Complex fields in SIP messages.

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
from six import (binary_type as bytes, add_metaclass)
from ..deepclass import (DeepClass, dck)
from ..parse import (Parser, ParsedPropertyOfClass)
from ..util import (BytesGenner, CCPropsFor, TwoCompatibleThree)
from ..transport import SOCK_TYPE_IP_NAMES
from ..vb import ValueBinder
from .components import (DNameURI, Host)
from . import defaults
from .param import (Parameters, Param)
from .prot import (bdict, Incomplete, protocols)

log = logging.getLogger(__name__)

sentinel = type('FieldNoAttributeSentinel', (), {})()


@add_metaclass(CCPropsFor(("delegateattributes", "parseinfo")))
@TwoCompatibleThree
class Field(
        DeepClass("_fld_", {
            "value": {},
            "parameters": {
                dck.descriptor: ParsedPropertyOfClass(Parameters),
                dck.gen: Parameters}
        }),
        Parser,
        BytesGenner,
        ValueBinder):

    # For headers that delegate properties, these are the properties to
    # delegate. Note that these are cumulative, so subclasses declaring their
    # own delegateattributes get added to these.
    delegateattributes = ["parameters"]

    # parseinfo is also cumulative, so any values set here will be overridden
    # if re-set in subclasses.
    parseinfo = {
        Parser.Pattern:
            # TODO: this is very coarse and could be improved. In particular it
            # does not cope with angle quoted URIs or double quoted display
            # names which contain semicolons.
            b"([^;]+)"  # String value.
            b"(.*)"  # Parameters.
            b"",
        Parser.Mappings:
            [("value",),
             ("parameters", Parameters)]
    }

    def bytesGen(self):
        yield bytes(self.value)
        yield bytes(self.parameters)

    def __setattr__(self, attr, val):
        if attr in Param.types:
            return setattr(self.parameters, attr, val)
        if attr != 'value':
            delval = getattr(self, 'value', sentinel)
            if delval is not sentinel:
                delattrs = getattr(delval, 'delegateattributes', sentinel)
                if delattrs is not sentinel and attr in delattrs:
                    return setattr(delval, attr, val)

        super(Field, self).__setattr__(attr, val)

    def __repr__(self):
        return (
            "{0.__class__.__name__}(value={0.value!r}, "
            "parameters={0.parameters!r})"
            "".format(self))


class DNameURIField(
        DeepClass("_dnurf_", {
            "value": {
                dck.gen: DNameURI,
                dck.descriptor: ParsedPropertyOfClass(DNameURI)}
        }),
        Field):
    delegateattributes = (
        "displayname", "uri", "aor", "host", "username", "address", "port")
    vb_dependencies = (("value", delegateattributes),)

    parseinfo = {
        Parser.Pattern:
            b"(%(name_addr)s|%(addr_spec)s)"  # String value.
            b"((?:;%(generic_param)s)*)"  # Parameters.
            b"" % bdict,
        Parser.Mappings:
            [("value", DNameURI),
             ("parameters", Parameters)],
        Parser.Repeats: True
    }


class ViaField(
        DeepClass("_vf_", {
            "host": {
                dck.descriptor: ParsedPropertyOfClass(Host), dck.gen: Host
            },
            "protocol": {
                dck.check: lambda pcl: pcl in protocols,
                dck.gen: lambda: defaults.sipprotocol
            },
            "transport": {
                dck.check: lambda tp: tp in SOCK_TYPE_IP_NAMES,
                dck.gen: lambda: defaults.transport
            }
        }),
        Field):
    """Via               =  ( "Via" / "v" ) HCOLON via-parm *(COMMA via-parm)
    via-parm          =  sent-protocol LWS sent-by *( SEMI via-params )
    via-params        =  via-ttl / via-maddr
                         / via-received / via-branch
                         / via-extension
    via-ttl           =  "ttl" EQUAL ttl
    via-maddr         =  "maddr" EQUAL host
    via-received      =  "received" EQUAL (IPv4address / IPv6address)
    via-branch        =  "branch" EQUAL token
    via-extension     =  generic-param
    """

    vb_dependencies = (
        ("host", ("address", "port")),)

    parseinfo = {
        Parser.Pattern:
            b"(%(protocol_name)s%(SLASH)s%(protocol_version)s)"
            b"%(SLASH)s"
            b"(%(transport)s)"
            b"%(LWS)s"
            b"(%(sent_by)s)"
            b"(%(SEMI)s%(generic_param)s)*"  # Parameters.
            b"" % bdict,
        Parser.Mappings:
            [("protocol", lambda x: x.replace(b" ", b"")),
             ("transport",),
             ("host", Host),
             ("parameters", Parameters)],
        Parser.Repeats: True
    }

    def bytesGen(self):
        pt = self.protocol
        if pt is None:
            raise Incomplete("Via header has not protocol.")
        yield bytes(pt)
        yield b'/'
        tp = self.transport
        if tp is None:
            raise Incomplete("Via header has no transport.")
        yield bytes(tp)
        yield b' '

        ht = self.host
        if ht is None:
            raise Incomplete("Via header has no host.")
        hbytes = bytes(ht)
        if not hbytes:
            raise Incomplete("Via header has no or 0-length host.")
        yield hbytes
        for bs in self.parameters.safeBytesGen():
            yield bs
