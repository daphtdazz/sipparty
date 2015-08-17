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
import six
from six import (binary_type as bytes, itervalues, add_metaclass)
import random
import logging
import prot
from numbers import Integral
from sipparty import (util, vb, parse, ParsedPropertyOfClass)
from sipparty.transport import SOCK_TYPE_IP_NAMES
from sipparty.deepclass import (DeepClass, dck)
import components
from components import (DNameURI, Host)
from request import Request
import defaults
from param import (Parameters, Param)
from prot import Incomplete

# More imports at end of file.

log = logging.getLogger(__name__)


@add_metaclass(util.CCPropsFor(("delegateattributes", "parseinfo")))
@util.TwoCompatibleThree
class Field(
        DeepClass("_fld_", {
            "value": {},
            "parameters": {
                dck.descriptor: ParsedPropertyOfClass(Parameters),
                dck.gen: Parameters}
        }),
        parse.Parser, vb.ValueBinder):

    # For headers that delegate properties, these are the properties to
    # delegate. Note that these are cumulative, so subclasses declaring their
    # own delegateattributes get added to these.
    delegateattributes = ["parameters"]

    # parseinfo is also cumulative, so any values set here will be overridden
    # if re-set in subclasses.
    parseinfo = {
        parse.Parser.Pattern:
            # TODO: this is very coarse and could be improved. In particular it
            # does not cope with angle quoted URIs or double quoted display
            # names which contain semicolons.
            "([^;]+)"  # String value.
            "(.*)"  # Parameters.
            "",
        parse.Parser.Mappings:
            [("value",),
             ("parameters", Parameters)]
    }

    def bytesGen(self, value):
        yield bytes(value)
        for pval in itervalues(self.parameters):
            yield bytes(pval)

    def __bytes__(self):
        rs = b";".join(self.bytesGen(self.value))
        return rs

    def __setattr__(self, attr, val):
        if attr in Param.types:
            return setattr(self.parameters, attr, val)
        if attr != "value" and hasattr(self, "value"):
            delval = self.value
            if (hasattr(delval, "delegateattributes") and
                    attr in delval.delegateattributes):
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
        parse.Parser.Pattern:
            "({name_addr}|{addr_spec})"  # String value.
            "((?:;{generic_param})*)"  # Parameters.
            "".format(**prot.__dict__),
        parse.Parser.Mappings:
            [("value", DNameURI),
             ("parameters", Parameters)],
        parse.Parser.Repeats: True
    }


class ViaField(
        DeepClass("_vf_", {
            "host": {
                dck.descriptor: ParsedPropertyOfClass(Host), dck.gen: Host
            },
            "protocol": {
                dck.check: lambda pcl: pcl in prot.protocols,
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
        parse.Parser.Pattern:
            "({protocol_name}{SLASH}{protocol_version})"
            "{SLASH}"
            "({transport})"
            "{LWS}"
            "({sent_by})"
            "({SEMI}{generic_param})*"  # Parameters.
            "".format(**prot.__dict__),
        parse.Parser.Mappings:
            [("protocol", None, lambda x: x.replace(" ", "")),
             ("transport",),
             ("host", components.Host),
             ("parameters", Parameters)],
        parse.Parser.Repeats: True
    }

    def __bytes__(self):
        pt = self.protocol
        if pt is None:
            raise Incomplete("Via header has not protocol.")
        tp = self.transport
        if tp is None:
            raise Incomplete("Via header has no transport.")

        ht = self.host
        if ht is None:
            raise Incomplete("Via header has no host.")
        hbytes = bytes(ht)
        if not hbytes:
            raise Incomplete("Via header has no or 0-length host.")
        vbytes = b"{pt}/{tp} {hbytes}".format(**locals())

        rs = b";".join(self.bytesGen(vbytes))
        return rs
