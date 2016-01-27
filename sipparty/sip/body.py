"""body.py

Code for handling different SIP body types. Different body types can be added
in separate files but they should be imported directly into this file so that
the automatic subclass generation can work.

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
from ..deepclass import (DeepClass, dck)
from ..parse import Parser
from ..util import BytesGenner

log = logging.getLogger(__name__)


class Body(
        DeepClass("_bdy_", {
            "type": {dck.check: lambda x: isinstance(x, bytes)},
            "content": {
                dck.gen: lambda: b'',
                dck.check: lambda x: isinstance(x, bytes)}
        }),
        Parser, BytesGenner):

    parseinfo = {
        Parser.Pattern:
            b'(.*)',
        Parser.Mappings: [
            ("content",),
        ]
    }

    def bytesGen(self):
        yield self.content
