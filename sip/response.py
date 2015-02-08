"""response.py



Copyright David Park 2015.

"""
import re
import logging
import prot
import defaults
import components
from parse import Parser
import _util
import vb
from header import Header
import pdb

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
    codemessage = _util.GenerateIfNotSet("codemessage")
