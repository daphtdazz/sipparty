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
import six
import random
import logging
import _util
import vb
import prot
from parse import Parser

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class Parameters(Parser, vb.ValueBinder, dict):
    """Class representing a list of parameters on a header or other object.
    """
    parseinfo = {
        Parser.Pattern: "^(.*)$"
    }

    def __init__(self):
        super(Parameters, self).__init__()
        self.parms = {}

    def __setattr__(self, attr, val):
        super(Parameters, self).__setattr__(attr, val)
        if attr in Param.types:
            if val is None:
                if attr in self:
                    del self[attr]
            else:
                self[attr] = val

    def __getattr__(self, attr):

        if attr in self:
            return self[attr]

        sp = super(Parameters, self)
        try:
            return sp.__getattr__(attr)
        except AttributeError:
            raise AttributeError(
                "%r instance has no attribute %r: parameters contained are "
                "%r.", (
                    self.__class__.__name__, attr, self.keys()))

    def parsecust(self, string, mo):

        parms = string.lstrip(";").split(";")
        log.debug("Parameters: %r", parms)

        for parm in parms:
            newp = Param.Parse(parm)
            self[newp.name] = newp


@six.add_metaclass(_util.attributesubclassgen)
@_util.TwoCompatibleThree
class Param(Parser, vb.ValueBinder):

    types = _util.Enum(("branch", "tag",), normalize=lambda x: x.lower())

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

    def __bytes__(self):
        if not hasattr(self, "value") and hasattr(self, "newvalue"):
            self.value = self.newvalue()
        return b"{self.name}={self.value}".format(self=self)

    def __eq__(self, other):
        log.debug("Param %r ?= %r", self, other)
        if self.__class__ != other.__class__:
            return False

        if self.value != other.value:
            return False

        return True

    def __repr__(self):
        return "%s(value=%r)" % (self.__class__.__name__, self.value)


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
