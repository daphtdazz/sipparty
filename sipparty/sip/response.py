"""response.py

Implements the start line of a SIP response message.

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

from sipparty import (parse, util, vb)
import prot
import defaults
import components
from parse import Parser
from header import Header

log = logging.getLogger(__name__)


class Response(Parser, vb.ValueBinder):
    """Response line class, such as
    200 INVITE
    """

    # Parse description.
    parseinfo = {
        Parser.Pattern:
            "([^\s]+)"  # The protocol.
            " "
            "(\d+)"  # The response code.
            " "
            "(.+)$",  # The reason
        Parser.Mappings:
            [("protocol",),
             ("code", int),  # The code should be an int.
             ("codemessage",)],
    }

    @classmethod
    def MessageForCode(cls, code):
        if code in prot.ResponseCodeMessages:
            return prot.ResponseCodeMessages[code]

        category_code = code / 100
        if category_code in prot.ResponseCodeMessages:
            return prot.ResponseCodeMessages

        raise prot.ProtocolError("Unknown response code %d" % code)

    def __str__(self):
        return "{self.protocol} {self.code} {self.codemessage}".format(
            self=self)

    def __init__(self, code=None):
        super(Response, self).__init__()
        if code is not None:
            try:
                self.code = int(code)
            except ValueError:
                raise ValueError("Response code %r not an integer" % code)
        self.protocol = None
        self.codemessage = None

    def generate_codemessage(self):
        return self.MessageForCode(self.code)
    codemessage = util.GenerateIfNotSet("codemessage")
