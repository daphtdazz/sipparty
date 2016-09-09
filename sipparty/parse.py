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
from __future__ import absolute_import

import re
import logging
from six import (binary_type as bytes, iteritems, PY2)
from .util import abytes, profile

log = logging.getLogger(__name__)


class ParseError(Exception):
    pass


class ParsedProperty(object):
    """This descriptor overrides set, such that if a value that is of binary
    type is set, instead of setting it directly, the `Parse` method of the
    Parser subclass is called instead."""

    def __init__(self, attr, cls):
        assert isinstance(cls, type) and hasattr(cls, "Parse"), (
            "Only subclasses of Parser may be used for ParsedProperty "
            "classes.")
        self._pp_attr = attr
        self._pp_class = cls

    def __get__(self, obj, cls):
        assert obj is not None, "ParsedProperty only applicable for instances."
        return getattr(obj, self._pp_attr)

    def __set__(self, obj, val):
        log.debug(
            'Set %s instance for attribute %s on %s instance',
            type(val).__name__, self._pp_attr, type(obj).__name__)
        atr = self._pp_attr
        if val is None:
            log.debug(
                "Set None for %r instance attribute %r",
                obj.__class__.__name__, atr)
            return setattr(obj, atr, val)

        if not PY2 and isinstance(val, str):
            val = abytes(val)

        cls = self._pp_class
        if isinstance(val, bytes):
            val = cls.Parse(val)
        else:
            if not isinstance(val, cls):
                raise TypeError(
                    "Cannot set unparseable %r instance for attribute %r of "
                    "%r instance." % (val.__class__.__name__, atr, cls))
        setattr(obj, atr, val)


def ParsedPropertyOfClass(cls):

    class _ParsedPropertyOfClass(ParsedProperty):

        def __init__(self, name, *args, **kwargs):
            super(_ParsedPropertyOfClass, self).__init__(
                name, cls, *args, **kwargs)

    return _ParsedPropertyOfClass


class Parser(object):
    """This mixin class provides a way of parsing hierarchical text into an
    object graph using regular expressions.

    A parse is triggered by a subclass of Parser calling the class method
    Parse. The result of this will either be a ParseError raised because the
    parse failed, or an instance of the subclass.

    ## Basic example.

    The simplest example is a class that creates an instance of itself and
    configures some attributes based on the values in the data.

    For example:

        class KeyValue(Parser):
            parseinfo = {
                Parser.Pattern:
                    b"(.+):(.+)",
                Parser.Mappings:
                    [("key",),
                     ("value",)]
            }

        kv = KeyValue.Parse("a:b")
        kv.key
        > "a"
        kv.value
        > "b"

        Attributes may be specified more than and

    ### Attribute customization

    To get more complicated object graphs, constructors for the attributes may
    be used. For example:

    class KeyValue(Parser):
        ...
            Parser.Mappings:
                [("key", Key),
                 ("value", Value)]
        ...

    kv = KeyValue.Parse("a:b")
    kv.key
    > Key("a")
    kv.value
    > Value("b")

    The index into the mapping corresponds to the group from the regular
    expression, starting at one. So in the above case, the first "(.+)" from
    the pattern is passed to Key.Parse(), and the second "(.+)" is passed to
    Value.Parse().

    If 'Key' had had a Parse method, then that would have been called to
    generate the instance. Otherwise 'Key' itself would have been called.

    ## Constructor customization

    Instead of looking for a Parse method in the class, or calling the class
    itself to construct the instance, a constructor (a callable) can be
    specified in the parseinfo dictionary:

        ...
            Parser.Constructor:
                (1, lambda a: ConstructObject(a))
        ...

    Here the first item in the tuple indicates the text group from the pattern
    that should be passed to the constructor as the single argument.

    This is useful for example when you want to create subclass B of the Parser
    subclass A instead of an instance of A directly.

    Once the object is constructed, any further attributes from the mapping
    list will be set on that object.

    ## Repetition.

    If you are parsing a sequence of items, then you can use the
    `Parser.Repeats` flag to indicate that the result of `Parse` should be a
    list of instances of the object, rather than just the object itself:

        ...
            Parser.Repeats: True
        ...

    In this case after the first match, the input text is cut down by the
    matched text is parsed again, until there is no input text remaining.

    ## Performance tweaks

    ### `PassMappingsToInit`

    By default, `Parser` finds the mappings from the string to parse, creates
    an instance using the generator, then sets the mappings one by one on the
    instance. A performance gain may be obtained however if the mappings may
    be passed into the `__init__` method of the class, which may avoid
    temporary objects being created and set before the mappings overwrite them,
    and thus make a performance gain.

    Set the `PassMappingsToInit` flag to `True` in the `parseinfo` dictionary
    of your class to gain this performance benefit if it is useful.

    E.g. `DeepClass` instances can have this flag set.

    """
    # These are keys that can be used in the parseinfo
    Pattern = "pattern"
    RE = "re"  # This will be compiled from the pattern automatically.
    Mappings = "mappings"
    # Class = "class"
    # Data = "data"
    Constructor = "constructor"
    Repeats = "repeat"
    PassMappingsToInit = "pass mappings to init"

    @classmethod
    def ParseFail(cls, string, *args, **kwargs):
        log.debug("Parse failure of message %r", string)
        for arg in args:
            log.debug(arg)
        for key, val in iteritems(kwargs):
            log.debug("%r=%r", key, val)
        raise ParseError(
            "{cls.__name__!r} type failed to parse text {string!r}."
            "".format(**locals()))

    @classmethod
    def SimpleParse(cls, string):
        if not hasattr(cls, "parseinfo"):
            raise TypeError(
                "{cls.__name__!r} does not support parsing (has no "
                "'parseinfo' field)."
                "".format(**locals()))

        pi = cls.parseinfo
        if Parser.RE not in pi:
            # not compiled yet.
            try:
                ptrn = pi[Parser.Pattern]
            except KeyError:
                raise TypeError(
                    "{0!r} does not have a Parser.Pattern in its "
                    "'parseinfo' dictionary.".format(cls))
            log.debug("  compile pattern.")
            try:
                pi[Parser.RE] = re.compile(ptrn)
            except re.error:
                log.error("Class %r pattern failed to compile:", cls.__name__)
                log.error("%r", ptrn)
                raise
            log.debug("  compile done.")

        pre = pi[Parser.RE]
        log.debug("  match")
        mo = pre.match(string)
        log.debug("  match done")
        if mo is None:
            cls.ParseFail(string, "Pattern was %r" % pi[Parser.Pattern])

        if len(mo.group(0)) != len(string):
            cls.ParseFail(string, "Did not match the whole pattern: %r" % (
                pi[Parser.Pattern],))

        return mo

    @classmethod
    @profile
    def Parse(cls, string):
        """The aim of this class method is to produce a fully initialized
        instance or list of instances of a subclass of Parser from some text.
        If it fails to parse the text it should raise a ParseError. Subclasses
        may wish to override this method to do custom parsing (perhaps they
        don't want to return instances of themselves).
        """
        pi = cls.parseinfo

        log.debug("%r Parse.", cls.__name__)

        if not isinstance(string, bytes):
            raise TypeError(
                'String to parse of type %r is not a bytes-like type.' %
                type(string))

        if Parser.Repeats in pi and pi[Parser.Repeats]:
            log.debug("  repeats")
            result = []
            repeats = True
        else:
            log.debug("  does not repeat")
            repeats = False

        while len(string) > 0:
            log.debug("  %r", string)
            mo = cls.SimpleParse(string)

            if Parser.Constructor in pi:
                constructor_tuple = pi[Parser.Constructor]
                log.debug("  constructor: %r.", constructor_tuple)

                constructor_gp = constructor_tuple[0]
                constructor_func = constructor_tuple[1]
                constructor_data = mo.group(constructor_gp)
                obj = constructor_func(constructor_data)
                if obj is None:
                    cls.ParseFail(
                        string,
                        "Could not construct the object from the data.")
                obj.parse(string, mo)
            elif pi.get(Parser.PassMappingsToInit, False):
                log.debug("  initialize class.")
                attrs = cls.parsemappings(mo, pi[Parser.Mappings])
                obj = cls(**attrs)
                getattr(obj, 'parsecust', lambda str_, mo_: None)(string, mo)
            else:
                obj = cls()
                obj.parse(string, mo)

            if not repeats:
                log.debug("  finished.")
                result = obj
                break

            result.append(obj)
            assert mo is not None, (
                "A repeating parser failed a match that didn't cause an "
                "exception.")
            string = string[len(mo.group(0)):]

        log.debug("Parse result %r", result)
        return result

    def parse(self, string, mo=None):

        log.debug("%r parse:", self.__class__.__name__)
        log.debug("  %r", string)

        if mo is None:
            mo = self.SimpleParse(string)

        if Parser.Mappings in self.parseinfo:
            mappings = self.parseinfo[Parser.Mappings]
            avs = self.parsemappings(mo, mappings)
            for attr, val in iteritems(avs):
                setattr(self, attr, val)

        # Finally do parsecust, if specified.
        if hasattr(self, "parsecust"):
            log.debug(
                "Parse to parsecust of %r instance", self.__class__.__name__)
            self.parsecust(string=string, mo=mo)

    @classmethod
    def parsemappings(cls, mo, mappings):
        """Return dictionary of mappings of attribute to value to set."""
        attr_vals = {}
        for mapping, gpnum in zip(mappings, range(1, len(mappings) + 1)):
            if mapping is None:
                continue

            log.debug("  group %d mapping %r", gpnum, mapping)
            data = mo.group(gpnum)
            if not data:
                # No data in this group so nothing to parse. If a group can
                # have no data then that implies this mapping is optional.
                log.debug("  no data")
                continue

            def gen(x):
                return x
            attr = mapping[0]
            log.debug("  attribute %r", attr)

            mapping_len = len(mapping)
            if mapping_len > 1:
                max_mapping_len = 2
                if mapping_len > max_mapping_len:
                    raise ValueError(
                        'Parser mapping %r has unexpected entries (expected '
                        'length was %d)' % (mapping, max_mapping_len))

                new_gen = mapping[1]
                if new_gen is not None:
                    log.detail('Use generator %r of type %r', gen, type(gen))
                    gen = new_gen

            if hasattr(gen, 'Parse'):
                log.detail('Generator is actually a Parser.')
                gen = gen.Parse

            log.debug("  raw text %r", data)
            tdata = gen(data)
            log.debug("  generated data %r", tdata)
            attr_vals[attr] = tdata

        return attr_vals
