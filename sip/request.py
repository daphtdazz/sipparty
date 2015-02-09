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
import re
import logging
import prot
import defaults
import components
import parse
import _util
import vb
from header import Header
import pdb

log = logging.getLogger(__name__)


class Request(parse.Parser, vb.ValueBinder):
    """Enumeration class generator"""

    types = _util.Enum(
        ("ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"),
        normalize=_util.upper)

    # This gives me case insensitive subclass instance creation and type-
    # checking.
    __metaclass__ = _util.attributesubclassgen

    # "type" is a descriptor that returns the type (e.g. ACK or BYE) based on
    # the class type, i.e. by removing "Request" from the class type.
    type = _util.ClassType("Request")

    # Parse description.
    parseinfo = {
        parse.Parser.Pattern:
            "({0})"
            " "
            "([^ ]*|<[^>]*>)"  # The uri.
            " "
            "([\w\d./]+)$"  # The protocol
            "".format("|".join(types)),
        parse.Parser.Constructor:
            (1, lambda a: getattr(Request, a)(autofill=False)),
        parse.Parser.Mappings:
            [None,  # First group is for the constructor.
             ("uri", components.URI, lambda x: x.strip("<>")),
             ("protocol",)],
    }

    def __str__(self):
        return "{self.type} {self.uri} {self.protocol}".format(self=self)

    def __init__(self, uri=None, protocol=defaults.sipprotocol, autofill=True):
        super(Request, self).__init__()
        if autofill and uri is None:
            uri = components.URI()

        for prop in ("uri", "protocol"):
            setattr(self, prop, locals()[prop])
