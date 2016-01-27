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
import logging
from six import add_metaclass
from ..deepclass import (DeepClass, dck)
from ..parse import (ParsedPropertyOfClass, Parser)
from ..util import (
    abytes, astr, attributesubclassgen, ClassType, TwoCompatibleThree)
from ..vb import ValueBinder
from . import defaults
from .components import (URI)
from .prot import (bdict, protocols, RequestTypes)

log = logging.getLogger(__name__)


@add_metaclass(attributesubclassgen)
@TwoCompatibleThree
class Request(
        DeepClass("_rq_", {
            "uri": {dck.descriptor: ParsedPropertyOfClass(URI), dck.gen: URI},
            "protocol": {
                dck.check: lambda pcl: pcl in protocols,
                dck.gen: lambda: defaults.sipprotocol
            }
        }),
        Parser, ValueBinder):
    """Encapsulates a SIP method request line.

    Request-Line  =  Method SP Request-URI SP SIP-Version CRLF
    """

    vb_dependencies = (
        ("uri", ("aor", "username", "host", "address", "port")),
    )

    types = RequestTypes.enum()

    # Parse description.
    parseinfo = {
        Parser.Pattern: (
            b'(%(Method)s)%(SP)s(%(Request_URI)s)%(SP)s(%(SIP_Version)s)'
            b'' % bdict),
        Parser.Constructor:
            (1, lambda a: getattr(Request, astr(a))()),
        Parser.Mappings:
            [None,  # First group is for the constructor.
             ("uri", URI),
             ("protocol",)],
    }

    type = ClassType("Request")

    def __bytes__(self):
        return b'%s %s %s' % (abytes(self.type), self.uri, self.protocol)

    def __repr__(self):
        return (
            "{0.__class__.__name__}(uri={0.uri!r}, protocol={0.protocol!r})"
            "".format(self))

Request.addSubclassesFromDict(locals())
