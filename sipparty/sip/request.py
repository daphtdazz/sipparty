"""request.py

Implements the request line of a SIP message.

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

from sipparty import (parse, util, vb)
import prot
import defaults
import components

log = logging.getLogger(__name__)
bytes = six.binary_type


@six.add_metaclass(util.attributesubclassgen)
@util.TwoCompatibleThree
class Request(parse.Parser, vb.ValueBinder):
    """Encapsulates a SIP method request line.

    Request-Line  =  Method SP Request-URI SP SIP-Version CRLF
    """

    types = prot.RequestTypes

    # "type" is a descriptor that returns the type (e.g. ACK or BYE) based on
    # the class type, i.e. by removing "Request" from the class type.
    type = util.ClassType("Request")

    # Parse description.
    parseinfo = {
        parse.Parser.Pattern: (
            b"({Method}){SP}({Request_URI}){SP}({SIP_Version})"
            "".format(**prot.__dict__)),
        parse.Parser.Constructor:
            (1, lambda a: getattr(Request, a)(autofill=False)),
        parse.Parser.Mappings:
            [None,  # First group is for the constructor.
             ("uri", components.URI),
             ("protocol",)],
    }

    def __bytes__(self):
        return "{self.type} {self.uri} {self.protocol}".format(self=self)

    def __init__(self, uri=None, protocol=defaults.sipprotocol, autofill=True):
        super(Request, self).__init__()
        if autofill and uri is None:
            uri = components.URI()

        for prop in ("uri", "protocol"):
            setattr(self, prop, locals()[prop])

    def __repr__(self):
        return (
            "{0.__class__.__name__}(uri={0.uri!r}, protocol={0.protocol!r})"
            "".format(self))

Request.addSubclassesFromDict(locals())
