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
import logging
import _util
import vb
import prot
from parse import Parser

log = logging.getLogger(__name__)


class SDPBody(Parser, vb.ValueBinder, dict):

    parseinfo = {
        Parser.Pattern:
            "^(([^{0}]+){0})$"
            "".format(prot.EOL)
    }

    def __init__(self):
        super(SDPBody, self).__init__()
        # This will be a dictionary of lists keyed on sdp type.
        self.lines = {}

    def __setattr__(self, attr, val):
        super(SDPBody, self).__setattr__(attr, val)
        if attr in SDPLine.types:
            if attr not in self:
                self[attr] = []
            self[attr][0] = val

    def __str__(self):

        all_lines = [
            line for list in self.lines.itervalues() for line in list]

        return prot.EOF.join(all_lines)


class SDPLine(object):
    types = _util.Enum(
        ("v", "o", "s", "i", "u", "e", "p", "c", "b", "z", "k", "a", "m"),
        normalize=lambda x: x.lower())
