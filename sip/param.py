"""param.py

Function for dealing with parameters of SIP headers.

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
import random
import logging
import _util
import vb
import prot
from parse import Parser

log = logging.getLogger(__name__)


class Parameters(Parser, vb.ValueBinder, dict):

    parseinfo = {
        Parser.Pattern: "^(.*)$"
    }

    def __init__(self):
        super(Parameters, self).__init__()
        self.parms = {}

    def __setattr__(self, attr, val):
        super(Parameters, self).__setattr__(attr, val)
        if attr in Param.types:
            self[attr] = val

    def parsecust(self, string, mo):

        parms = string.lstrip(";").split(";")
        log.debug("Parameters: %r", parms)

        for parm in parms:
            newp = Param.Parse(parm)
            self[newp.name] = newp


class Param(Parser, vb.ValueBinder):

    types = _util.Enum(("branch", "tag",), normalize=lambda x: x.lower())

    __metaclass__ = _util.attributesubclassgen

    parseinfo = {
        Parser.Pattern:
            "\s*([^\s=]+)"
            "\s*=\s*"
            "(.+)",
        Parser.Constructor:
            (1, lambda x: getattr(Param, x)()),
        Parser.Mappings:
            [None,
             ("value",)]
    }

    name = _util.ClassType("Param")

    def __init__(self, value=None):
        super(Param, self).__init__()
        self.values = []
        if value is not None:
            self.value = value

    def __str__(self):
        if not hasattr(self, "value") and hasattr(self, "newvalue"):
            self.value = self.newvalue()
        return "{self.name}={self.value}".format(self=self)


class BranchParam(Param):

    BranchNumber = random.randint(1, 10000)

    def __init__(self, startline=None, branch_num=None):
        super(BranchParam, self).__init__()
        self.startline = startline
        if branch_num is None:
            branch_num = BranchParam.BranchNumber
            BranchParam.BranchNumber += 1
        self.branch_num = branch_num

    def generate_value(self):
        if not hasattr(self, "startline") or not hasattr(self, "branch_num"):
            raise AttributeError(
                "{self.__class__.__name__!r} needs attributes 'startline' and "
                "'branch_num' to autogenerate 'value'."
                "".format(**locals()))
        str_to_hash = "{0}-{1}".format(str(self.startline), self.branch_num)
        the_hash = hash(str_to_hash)
        if the_hash < 0:
            the_hash = - the_hash
        nv = "{0}{1:x}".format(prot.BranchMagicCookie, the_hash)
        log.debug("New %r value %r", self.__class__.__name__, nv)
        return nv
    value = _util.GenerateIfNotSet("value")

    def __setattr__(self, attr, val):
        if attr in ("startline", "branch_num"):
            if hasattr(self, "value"):
                del self.value
        super(BranchParam, self).__setattr__(attr, val)


class TagParam(Param):

    def __init__(self, tagtype=None):
        # tagtype could be used to help ensure that the From: and To: tags are
        # different all the time.
        super(TagParam, self).__init__()
        self.tagtype = tagtype

    def generate_value(self):
        # RFC 3261 asks for 32 bits of randomness. Expect random is good
        # enough.
        return "{0:08x}".format(random.randint(0, 2**32 - 1))
    value = _util.GenerateIfNotSet("value")
