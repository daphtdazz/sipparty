"""sdp.py

Code for handling Session Description Protocol

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
import logging
import _util
import vb
import prot
from parse import Parser

log = logging.getLogger(__name__)


class SDPNoSuchDescription(Exception):
    pass


@six.add_metaclass(_util.attributesubclassgen)
@_util.TwoCompatibleThree
class Line(Parser):
    types = _util.Enum((
        "v", "o", "s", "i", "u", "e", "p", "c", "b", "t", "z", "k", "a", "m"))
    longtypes = _util.Enum((
        "version",
        "owner",
        "sessionname",
        "info",
        "uri",
        "email",
        "phone",
        "connectioninfo",
        "bandwidthinfo",
        "time",
        "timezone",
        "encryptionkey",
        "attributes",
        "media"
    ))

    descvalpattern = (
        "([^{eol}]+)[{eol}]+".format(eol=prot.EOL)
    )
    parseinfo = {
        Parser.Pattern:
            # Each valpat has a single group in it, which covers the value of
            # the line.
            "([{types}])={valpat}[{eol}]+"
            "".format(types="".join(types), valpat=descvalpattern,
                      eol=prot.EOL),
        Parser.Constructor:
            (1, lambda t: getattr(Line, t)()),
        Parser.Mappings:
            [None,  # The type.
             ("value",)],
        Parser.Repeats: True
    }

    def __bytes__(self):
        return b"{self.type}={self.value}".format(self=self)


@_util.TwoCompatibleThree
class Body(Parser, vb.ValueBinder):
    """SDP is a thankfully tightly defined protocol, allowing this parser to
    be much more explicit. The main point is that there are 3 sections:

    Session Description (one)
    Time Description (one)
    Media Description (one or more)

    For sanity, sdp.Body expands the first two (so sdp.body.version gives you
    the version description), and the medias attribute is a list formed by
    parsing MediaDe2sc, which is a repeating pattern.

    The SDP spec says something about multiple session descriptions, but I'm
    making the initial assumption that in SIP there will only be one.
    """

    parseinfo = {
        Parser.Pattern:
            "(([^{eol}]+[{eol}]{{,2}})+)"
            "".format(eol=prot.EOL),
        Parser.Mappings:
            [("lines", Line)]
    }

    ZeroOrOne = b"?"
    ZeroPlus = b"*"
    OnePlus = b"+"
    validorder = (
        # Defines the order of SDP, and how many of each type there can be.
        # Note that for the time and media lines, there are subsidiary fields
        # which may follow, and the number of times they may follow are
        # denoted by the next flag in the tuple.
        (b"v", 1),
        (b"o", 1),
        (b"s", 1),
        (b"i", ZeroOrOne),  # Info line.
        (b"u", ZeroOrOne),
        (b"e", ZeroOrOne),
        (b"p", ZeroOrOne),
        (b"c", ZeroOrOne),
        (b"b", ZeroOrOne),
        (b"z", ZeroOrOne),  # Timezone
        (b"k", ZeroOrOne),  # Encryption key
        (b"a", ZeroPlus),  # Zero or more attributes.
        (b"tr", 1, ZeroPlus),  # Time descriptions followed by repeats.
        # Zero or more media descriptions, and they may have attributes.
        (b"micbka", ZeroPlus, ZeroOrOne, ZeroOrOne, ZeroOrOne, ZeroOrOne,
         ZeroPlus)
    )

    def __bytes__(self):

        all_lines = []
        for line in self.lines:
            all_lines.append(bytes(line))
        all_lines.append(b"")  # Always need an extra newline.
        return prot.EOL.join(all_lines)
