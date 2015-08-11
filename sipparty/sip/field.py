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
import random
import logging
import prot
from sipparty import (util, vb, parse, ParsedPropertyOfClass)
from sipparty.transport import SOCK_TYPE_IP_NAMES
from sipparty.deepclass import (DeepClass, dck)
import components
from components import (DNameURI, Host)
from request import Request
import defaults
import param

# More imports at end of file.

log = logging.getLogger(__name__)

bytes = six.binary_type


@six.add_metaclass(util.CCPropsFor(("delegateattributes", "parseinfo")))
@util.TwoCompatibleThree
class Field(parse.Parser, vb.ValueBinder):

    # For headers that delegate properties, these are the properties to
    # delegate. Note that these are cumulative, so subclasses declaring their
    # own delegateattributes get added to these.
    delegateattributes = ["parameters"]

    value = util.GenerateIfNotSet("value")

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
             ("parameters", param.Parameters)]
    }

    def __init__(self, value=None):
        super(Field, self).__init__()
        self.parameters = param.Parameters()
        if value is not None:
            self.value = value
        else:
            self.value = DNameURI()

    def __bytes__(self):
        rs = b"{self.value}".format(**locals())
        rslist = [rs]
        rslist.extend(
            [bytes(val) for val in self.parameters.itervalues()])
        log.debug(";.join(%r)", rslist)
        rs = b";".join(rslist)
        return rs

    def __setattr__(self, attr, val):
        if attr in param.Param.types:
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


class DNameURIField(Field):
    delegateattributes = (
        "uri", "aor", "host", "username", "address")
    vb_dependencies = (("value", delegateattributes),)

    parseinfo = {
        parse.Parser.Pattern:
            "({name_addr}|{addr_spec})"  # String value.
            "((?:;{generic_param})*)"  # Parameters.
            "".format(**prot.__dict__),
        parse.Parser.Mappings:
            [("value", components.DNameURI),
             ("parameters", param.Parameters)]
    }

    def __init__(self):
        super(DNameURIField, self).__init__(components.DNameURI())


class ViaField(
        DeepClass("_vf_", {
            "host": {
                dck.descriptor: ParsedPropertyOfClass(Host), dck.gen: Host
            },
            "protocol": {
                dck.check: lambda pcl: pcl in prot.protocols,
                dck.gen: lambda: defaults.sipprotocol
            },
            "transport":{
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

    delegateattributes = ("protocol", "transport", "host", "address", "port")
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
             ("parameters", param.Parameters)]
    }

    # We should always regen value because it is always a one-to-one mapping
    # onto protocol, transport and host.
    value = util.GenerateIfNotSet("value", alwaysregen=True)

    def generate_value(self):
        prottrans = "/".join((self.protocol, self.transport))

        if self.host is not None:
            log.debug("Viaheader host is %r %s.", self.host, self.host)
            hoststr = bytes(self.host)
            if len(hoststr) == 0:
                hoststr = None

        if hoststr is not None:
            rv = "{prottrans} {hoststr}".format(**locals())
        else:
            rv = "{prottrans}".format(**locals())
        log.debug("host:%s, prot: %s, trans: %r, Return %r",
                  self.host, self.protocol, self.transport, rv)
        return rv

    def __setattr__(self, attr, val):
        if False and attr in self.delegateattributes:
            if hasattr(self, "value"):
                del self.value
        super(ViaField, self).__setattr__(attr, val)


class CSeqField(Field):

    delegateattributes = ["number", "reqtype"]

    parseinfo = {
        parse.Parser.Pattern:
            "(\d+)"
            " "
            "([\w_-]+)$",  # No parameters.
        parse.Parser.Mappings:
            [("number", None, int),
             ("reqtype", None, lambda x: getattr(Request.types, x))]
    }

    @classmethod
    def GenerateNewNumber(cls):
        return random.randint(0, 2**31 - 1)

    def __init__(self, number=None, reqtype=None):
        super(CSeqField, self).__init__()
        self.number = number
        self.reqtype = reqtype

    def generate_number(self):
        return self.GenerateNewNumber()
    number = util.GenerateIfNotSet("number")

    def generate_value(self):
        return "{self.number} {self.reqtype}".format(self=self)
    value = util.GenerateIfNotSet("value", alwaysregen=True)

    def __setattr__(self, attr, val):
        """The CSeq depends on the number and the request line type, so if
        either changes then we need to invalidate the value."""
        if attr in ("number", "reqtype"):
            self.value = None
        super(CSeqField, self).__setattr__(attr, val)


class Max_ForwardsField(Field):
    delegateattributes = ["number"]

    def __init__(self, number=defaults.max_forwards):
        super(Max_ForwardsField, self).__init__()
        self.number = number
        self.bind("number", "value")
