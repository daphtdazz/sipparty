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
import logging
import re
from ..parse import Parser
from ..util import (DerivedProperty, TwoCompatibleThree)
from ..vb import ValueBinder
from . import defaults
from . import prot
from .prot import (bdict, ProtocolError, ResponseCodeMessages)

log = logging.getLogger(__name__)


@TwoCompatibleThree
class Response(Parser, ValueBinder):
    """Response line class, such as
    200 INVITE
    """

    # Parse description.
    parseinfo = {
        Parser.Pattern:
            b'(%(SIP_Version)s)%(SP)s(%(Status_Code)s)%(SP)s'
            b'(%(Reason_Phrase)s)' % bdict,
        Parser.Mappings:
            [('protocol',),
             ('code', int),
             ('codeMessage',)],
    }

    @classmethod
    def MessageForCode(cls, code):
        if code in ResponseCodeMessages:
            return ResponseCodeMessages[code]

        category_code = code / 100
        if category_code in ResponseCodeMessages:
            return ResponseCodeMessages

        raise ProtocolError('Unknown response code %d' % code)

    codeMessage = DerivedProperty(
        '_rsp_codeMessage', get='getCodeMessage')

    def getCodeMessage(self, underlyingValue):
        if underlyingValue is not None:
            return underlyingValue

        code = self.code
        if code is None:
            return None

        return self.MessageForCode(code)

    def __init__(self, code=None, codeMessage=None,
                 protocol=defaults.sipprotocol):
        super(Response, self).__init__()
        if code is not None:
            try:
                code = int(code)
            except ValueError:
                raise ValueError('Response code %r not an integer' % code)

        self.code = code
        self.protocol = protocol
        self.codeMessage = codeMessage

    def __bytes__(self):
        return b'%s %s %s' % (self.protocol, self.code, self.codeMessage)

    def __repr__(self):
        return (
            '{0.__class__.__name__}(code={0.code!r}, '
            'codeMessage={0.codeMessage!r}, protocol={0.protocol!r})'
            ''.format(self))
