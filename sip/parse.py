"""parse.py

Parsing mixin class for unpacking objects from regular expression based
pattern matching.

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
import re
import logging
import pdb

log = logging.getLogger(__name__)
log.level = logging.ERROR


class ParseError(Exception):
    pass


class Parser(object):

    # Special attribute in the parser description that causes us to get an
    # instance by asking the class for this attribute.
    # GenAttr = "_genattr"
    Pattern = "pattern"
    RE = "re"
    Mappings = "mappings"
    Class = "class"
    Data = "data"
    Constructor = "constructor"

    @classmethod
    def ParseFail(cls, string, *args, **kwargs):
        log.warning("Parse failure of message %r", string)
        for key, val in kwargs.iteritems():
            log.debug("%r=%r", key, val)
        raise ParseError(
            "{cls.__name__!r} type failed to parse text {string!r}. Extra "
            "info: {args}"
            "".format(**locals()))

    @classmethod
    def SimpleParse(cls, string):
        if not hasattr(cls, "parseinfo"):
            raise TypeError(
                "{cls.__name__!r} does not support parsing (has no "
                "'parseinfo' field)."
                "".format(**locals()))

        log.debug("SimpleParse with parseinfo %r", cls.parseinfo)

        pi = cls.parseinfo
        if Parser.RE not in pi:
            # not compiled yet.
            try:
                ptrn = pi[Parser.Pattern]
            except KeyError:
                pdb.set_trace()
                raise TypeError(
                    "{0!r} does not have a Parser.Pattern in its "
                    "'parseinfo' dictionary.".format(cls))
            log.debug("Compile re %s", ptrn)
            pi[Parser.RE] = re.compile(ptrn)

        pre = pi[Parser.RE]
        mo = pre.match(string)
        if mo is None:
            cls.ParseFail(string)

        return mo

    @classmethod
    def Parse(cls, string):
        log.debug("%r Parse %s", cls.__name__, string)

        mo = cls.SimpleParse(string)
        pi = cls.parseinfo
        if Parser.Constructor in pi:
            constructor_tuple = pi[Parser.Constructor]
            log.debug("Using constructor %r", constructor_tuple)
            constructor_gp = constructor_tuple[0]
            constructor_func = constructor_tuple[1]
            constructor_data = mo.group(constructor_gp)
            obj = constructor_func(constructor_data)
            if obj is None:
                cls.ParseFail(
                    string, "Could not construct the object from the data.")
        else:
            log.debug("No constructor: new version of class %r", cls.__name__)
            obj = cls()

        log.debug("Parse %r", obj)
        obj.parse(string, mo)
        return obj

    def parse(self, string, mo=None):
        log.debug("%r parse %s", self, string)

        if mo is None:
            mo = self.SimpleParse(string)

        if Parser.Mappings in self.parseinfo:
            mappings = self.parseinfo[Parser.Mappings]
            self.parsemappings(mo, mappings)

        if hasattr(self, "parsecust"):
            self.parsecust(string=string, mo=mo)

    def parsemappings(self, mo, mappings):
        log.debug("Apply mappings %r", mappings)
        for mapping, gpnum in zip(mappings, range(1, len(mappings) + 1)):
            if mapping is None:
                continue

            data = mo.group(gpnum)
            if not data:
                # No data in this group so nothing to parse. If a group can
                # have no data then that implies this mapping is optional.
                log.debug("No data for mapping %r", mapping)
                continue

            log.debug("Apply mapping %r to group %d", mapping, gpnum)
            attr = mapping[0]
            cls = str
            gen = lambda x: x
            if len(mapping) > 1:
                new_cls = mapping[1]
                if new_cls is not None:
                    cls = new_cls
            if len(mapping) > 2:
                gen = mapping[2]

            log.debug("  text %r", data)
            tdata = gen(data)
            log.debug("  result %r", tdata)
            try:
                if hasattr(cls, "Parse"):
                    obj = cls.Parse(tdata)
                else:
                    obj = cls(tdata)
            except TypeError:
                log.error(
                    "Error generating %r instance for attribute "
                    "%r. Perhaps it does not take at least one "
                    "argument in its constructor / initializer or "
                    "implement 'Parse'?", cls.__name__, attr)
                raise
            log.debug("  object %r", obj)
            setattr(self, attr, obj)
