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
from six import binary_type as bytes
from ..classmaker import classbuilder
from ..parse import (Parser)
from ..util import (
    abytes, astr, Enum, attributesubclassgen, BytesGenner, ClassType,
    DerivedProperty, TwoCompatibleThree)
from ..vb import ValueBinder
from .prot import (bdict, BranchMagicCookie, Incomplete)

log = logging.getLogger(__name__)


@classbuilder(
    bases=(
        Parser, BytesGenner, ValueBinder
    )
)
class Parameters:
    """Class representing a list of parameters on a header or other object.
    """
    parseinfo = {
        Parser.Pattern: b"(;%(generic_param)s)*" % bdict
    }

    def __init__(self):
        super(Parameters, self).__init__()
        self._parm_list = []

    def __eq__(self, other):
        if type(self) != type(other):
            return False

        if len(self) != len(other):
            return False

        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in self._parm_list
        )

    def __len__(self):
        return len(self._parm_list)

    def __repr__(self):
        return '%s(parameters=[%s])' % (
            type(self).__name__,
            ', '.join(
                repr(pp)
                for pp in self._parm_list
            )
        )

    def __setattr__(self, attr, val):
        if attr.startswith('_') or attr.startswith('vb'):
            return super(Parameters, self).__setattr__(attr, val)

        if val is None:
            # For a None val we don't want to create a new object.
            pass
        elif not isinstance(val, Param):
            if attr in Param.types:
                val = getattr(Param, attr)(val)
            else:
                # generic parameter
                val = Param(val)

        if attr not in self._parm_list:
            self._parm_list.append(attr)

        super(Parameters, self).__setattr__(attr, val)

    def parsecust(self, string, mo):
        parms = string.lstrip(b';').split(b';')
        log.debug("Parameters: %r", parms)

        for parm in parms:
            newp = Param.Parse(parm)
            setattr(self, newp.name, newp)

    def bytesGen(self):
        for key in self._parm_list:
            val = getattr(self, key)
            if val is None:
                log.detail('Skip None param, %s', key)
                continue

            log.detail('Add %s param ', key)
            yield b';'
            yield abytes(key)
            if val:
                yield b'='
                for by in val.safeBytesGen():
                    yield by


@TwoCompatibleThree
@classbuilder(
    bases=(
        Parser, BytesGenner, ValueBinder
    ),
    mc=attributesubclassgen
)
class Param:

    types = Enum(("branch", "tag",), normalize=lambda x: x.lower())

    parseinfo = {
        Parser.Pattern:
            b"\s*([^\s=]+)"
            b"\s*=\s*"
            b"(.+)",
        Parser.Constructor:
            (1, lambda x: getattr(Param, astr(x))()),
        Parser.Mappings:
            [None,
             ("value",)]
    }

    name = ClassType("Param")
    value = DerivedProperty("_prm_value", get="getValue")

    def __init__(self, value=None):
        super(Param, self).__init__()
        self.value = value

    def getValue(self, underlying_value):
        "Get the value. Subclasses should override."
        return underlying_value

    def bytesGen(self):
        log.debug("%r bytesGen", self.__class__.__name__)
        vv = self.value
        if vv is None:
            raise Incomplete('%s has no value so is incomplete' % (
                type(self).__name__,))
        yield bytes(vv)

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

    def __init__(self, value=None, startline=None, branch_num=None):
        super(BranchParam, self).__init__(value=value)
        self.startline = startline
        if branch_num is None:
            branch_num = BranchParam.BranchNumber
            BranchParam.BranchNumber += 1
        self.branch_num = branch_num

    def getValue(self, underlying_value):
        log.detail(
            'Get %r instance value, underlying is %r', self.__class__.__name__,
            underlying_value)

        if underlying_value is not None:
            return underlying_value

        sl, bn = (getattr(self, attr, None) for attr in (
            "startline", "branch_num"))
        if any(_ is None for _ in (sl, bn)):
            return None

        try:
            str_to_hash = b"%s-%d" % (bytes(self.startline), self.branch_num)
        except Incomplete:
            # So part of us is not complete. Return None.
            log.debug('Incomplete Branch Parameter')
            return None

        the_hash = hash(str_to_hash)
        if the_hash < 0:
            the_hash = - the_hash
        nv = b"%s%x" % (BranchMagicCookie, the_hash)
        log.debug("New %r value %r", self.__class__.__name__, nv)
        return nv


class TagParam(Param):
    """The dialog ID consists of a Call-ID value, a local tag and a remote tag.
    """

    def __init__(self, value=None, tagtype=None):
        # tagtype could be used to help ensure that the From: and To: tags are
        # different all the time.
        super(TagParam, self).__init__(value=value)
        self.tagtype = tagtype

    def getValue(self, underlying_value):
        log.detail(
            'Get %r instance value, underlying is %r', self.__class__.__name__,
            underlying_value)
        if underlying_value is not None:
            return underlying_value

        # RFC 3261 asks for 32 bits of randomness. Expect random is good
        # enough.
        value = b"%08x" % (random.randint(0, 2**32 - 1),)

        # The TagParam needs to learn its value and stick with it.
        self._prm_value = value
        return value

Param.addSubclassesFromDict(dict(locals()))
