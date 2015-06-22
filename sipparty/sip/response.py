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

from sipparty import (util, vb, Parser)
import prot
import defaults
import components
from header import Header

log = logging.getLogger(__name__)


@util.TwoCompatibleThree
class Response(Parser, vb.ValueBinder):
    """Response line class, such as
    200 INVITE
    """

    # Parse description.
    parseinfo = {
        Parser.Pattern:
            "({SIP_Version}){SP}({Status_Code}){SP}({Reason_Phrase})"
            "".format(**prot.__dict__),
        Parser.Mappings:
            [("protocol",),
             ("code", int),  # The code should be an int.
             ("codeMessage",)],
    }

    @classmethod
    def MessageForCode(cls, code):
        if code in prot.ResponseCodeMessages:
            return prot.ResponseCodeMessages[code]

        category_code = code / 100
        if category_code in prot.ResponseCodeMessages:
            return prot.ResponseCodeMessages

        raise prot.ProtocolError("Unknown response code %d" % code)

    codeMessage = util.DerivedProperty(
        "_rsp_codeMessage", get="getCodeMessage")

    def getCodeMessage(self, underlyingValue):
        if underlyingValue is not None:
            return underlyingValue

        return self.MessageForCode(self.code)

    def __init__(self, code=None, codeMessage=None,
                 protocol=defaults.sipprotocol):
        super(Response, self).__init__()
        if code is not None:
            try:
                code = int(code)
            except ValueError:
                raise ValueError("Response code %r not an integer" % code)

        self.code = code
        self.protocol = protocol
        self.codeMessage = codeMessage

    def __bytes__(self):
        return b"{0.protocol} {0.code} {0.codeMessage}".format(self)

    def __repr__(self):
        return (
            "{0.__class__.__name__}(code={0.code!r}, "
            "codeMessage={0.codeMessage!r}, protocol={0.protocol!r})"
            "".format(self))
