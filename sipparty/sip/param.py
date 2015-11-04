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
import logging
import random
from six import (itervalues, binary_type as bytes, add_metaclass)
from ..parse import (Parser)
from ..util import (
    BytesGenner, attributesubclassgen, TwoCompatibleThree, AsciiBytesEnum,
    ClassType, DerivedProperty)
from ..vb import ValueBinder
from .prot import (BranchMagicCookie, Incomplete)

log = logging.getLogger(__name__)


class Parameters(Parser, BytesGenner, ValueBinder, dict):
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

    def bytesGen(self):
        for pm in itervalues(self):
            yield b';'
            for by in pm.bytesGen():
                yield by


@add_metaclass(attributesubclassgen)
@TwoCompatibleThree
class Param(Parser, BytesGenner, ValueBinder):

    types = AsciiBytesEnum((b"branch", b"tag",), normalize=lambda x: x.lower())

    parseinfo = {
        Parser.Pattern:
            b"\s*([^\s=]+)"
            b"\s*=\s*"
            b"(.+)",
        Parser.Constructor:
            (1, lambda x: getattr(Param, x)()),
        Parser.Mappings:
            [None,
             ("value",)]
    }

    name = ClassType("Param")
    value = DerivedProperty("_prm_value", get="getValue")

    def __init__(self, value=None):
        super(Param, self).__init__()
        self.value = value

    def getValue(self, underlyingValue):
        "Get the value. Subclasses should override."
        return underlyingValue

    def bytesGen(self):
        log.debug("Param Bytes")
        yield bytes(self.name)
        yield b'='
        yield bytes(self.value)

    def __eq__(self, other):
        log.debug("Param %r ?= %r", self, other)
        if self.__class__ != other.__class__:
            return False

        if self.value != other.value:
            return False

        return True

    def __repr__(self):
        return "%s(value=%r)" % (
            # !!! TODO: self.value causes us to call bytes which may not
            # work...
            self.__class__.__name__, self.value)


class BranchParam(Param):
    """Branch parameter.

    The branch parameter identifies a request and response transaction. It is
    renewed for each request as per:

    https://tools.ietf.org/html/rfc3261#section-8.1.1.7

    and each ACK responding to 200 as per:

    https://tools.ietf.org/html/rfc3261#section-13.2.2.4
    """

    BranchNumber = random.randint(1, 10000)

    def __init__(self, startline=None, branch_num=None):
        super(BranchParam, self).__init__()
        self.startline = startline
        if branch_num is None:
            branch_num = BranchParam.BranchNumber
            BranchParam.BranchNumber += 1
        self.branch_num = branch_num

    def getValue(self, underlyingValue):
        if underlyingValue is not None:
            return underlyingValue

        if not hasattr(self, "startline") or not hasattr(self, "branch_num"):
            return None

        try:
            str_to_hash = b"{0}-{1}".format(
                bytes(self.startline), self.branch_num)
        except Incomplete:
            # So part of us is not complete. Return None.
            return None

        the_hash = hash(str_to_hash)
        if the_hash < 0:
            the_hash = - the_hash
        nv = b"{0}{1:x}".format(BranchMagicCookie, the_hash)
        log.debug("New %r value %r", self.__class__.__name__, nv)
        return nv


class TagParam(Param):
    """The dialog ID consists of a Call-ID value, a local tag and a remote tag.
    """

    def __init__(self, tagtype=None):
        # tagtype could be used to help ensure that the From: and To: tags are
        # different all the time.
        super(TagParam, self).__init__()
        self.tagtype = tagtype

    def getValue(self, underlyingValue):
        if underlyingValue is not None:
            return underlyingValue

        # RFC 3261 asks for 32 bits of randomness. Expect random is good
        # enough.
        value = b"{0:08x}" % (random.randint(0, 2**32 - 1),)

        # The TagParam needs to learn its value and stick with it.
        self._prm_value = value
        return value

Param.addSubclassesFromDict(dict(locals()))
