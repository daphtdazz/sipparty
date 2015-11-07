"""deepclass.py

Superclasses for classes which automatically create deep object graphs on
instantiation.

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
from collections import Callable
import inspect
import logging
from six import (iteritems, iterkeys)
from .util import (Enum, DerivedProperty)
from .vb import ValueBinder

log = logging.getLogger(__name__)
DeepClassKeys = Enum(("check", "get", "set", "gen", "descriptor",))
dck = DeepClassKeys


def DCProperty(tlp, name, attrDesc):
    internalName = tlp + name

    if dck.descriptor in attrDesc:
        dc = attrDesc[dck.descriptor]
        if dc is None:
            log.debug("%r doesn't want a descriptor", name)
            return None

        log.debug("%r uses descriptor %r", internalName, dc)
        return dc(internalName)

    dpdict = dict(attrDesc)
    for badKey in (dck.gen,):
        if badKey in dpdict:
            del dpdict[badKey]
    log.detail(
        "New derived property for %r underlying %r: with config %r", name,
        internalName, dpdict)
    return DerivedProperty(internalName, **dpdict)


def DeepClass(topLevelPrepend, topLevelAttributeDescs):
    """Creates a deep class type which
    """
    class DeepClass(object):

        for name, attrDescGen in iteritems(topLevelAttributeDescs):
            attrDesc = DCProperty(topLevelPrepend, name, attrDescGen)
            if attrDesc is None:
                continue
            locals()[name] = attrDesc

        # Careful that these don't become class attributes!
        del attrDescGen
        del attrDesc
        del name

        def __init__(self, **kwargs):

            clname = self.__class__.__name__
            log.detail("DeepClass %r init with kwargs: %r", clname,
                       kwargs)

            # Preload the top level attributes dictionary and our instance
            # dictionary.
            topLevelAttrArgs = {}
            sd = self.__dict__
            for tlName in iterkeys(topLevelAttributeDescs):
                sd[topLevelPrepend + tlName] = None
                topLevelAttrArgs[tlName] = [None, {}]

            log.detail("Start dict: %r", sd)

            # Initial pass to end with a dictionary like:
            # kwargs = {"topLevelAttribute_tlaSubAttribute1": subValue,
            #           "topLevelAttribute": value}
            # topLevelAttrArgs = {
            #     "topLevelAttribute": [
            #         value,  # May be None.
            #         {
            #            "tlaSubAttribute1": subValue,
            #         }
            #     ]
            # }
            # And with superKwargs just the unrecognised args to pass on to
            # super.
            superKwargs = dict(kwargs)
            for kwName, kwVal in iteritems(kwargs):
                topLevelAttrName, _, subAttr = kwName.partition("_")
                if topLevelAttrName not in topLevelAttributeDescs:
                    log.detail("Super kwarg %r", kwName)
                    continue

                log.detail("Deep class kwarg %r %r", kwName, kwVal)
                del superKwargs[kwName]

                tlaa = topLevelAttrArgs[topLevelAttrName]

                if len(_) != 0:
                    if len(subAttr) == 0:
                        raise KeyError(
                            "Attribute %r of %r instance not a valid "
                            "subattribute of attribute %r." % (
                                kwName, clname,
                                topLevelAttrName))
                    tlaa[1][subAttr] = kwVal
                else:
                    tlaa[0] = kwVal

            # See if we have any delegates to pass to.
            log.debug('Check VB dependencies')
            dele_attrs = {}
            if hasattr(self, "vb_dependencies"):
                if not isinstance(self, ValueBinder):
                    raise TypeError(
                        "%r instance has 'vb_dependencies' set but is not a "
                        "subclass of 'ValueBinder'" % (
                            self.__class__.__name__,))
                vbds = self.vb_dependencies
                allDeleAttrs = set([
                    attr for attrs in vbds for attr in attrs[1]])
                for kwName, kwVal in iteritems(dict(superKwargs)):
                    if kwName not in allDeleAttrs:
                        continue
                    log.debug("Delegate attribute saved: %r", kwName)
                    dele_attrs[kwName] = kwVal
                    del superKwargs[kwName]

            # Call super init.
            log.detail("super init dict: %r", superKwargs)
            super(DeepClass, self).__init__(**superKwargs)

            # Loop through the entries for the top level attributes, and
            # generate values for anything that's missing.
            log.detail(
                "Recurse to %r top level attributes: %r",
                clname, topLevelAttrArgs)
            for tlattr, (tlval, tlsvals) in iteritems(topLevelAttrArgs):
                if tlval is None:
                    if (
                            hasattr(self, tlattr) and
                            getattr(self, tlattr) is not None):
                        log.debug(
                            "No need to generate %r for %r: already set "
                            "(probably by bindings) to %r.", tlattr,
                            clname, getattr(self, tlattr))
                        continue

                    tlad = topLevelAttributeDescs[tlattr]
                    if dck.gen not in tlad:
                        log.debug(
                            "%r attribute not set and doesn't have generator",
                            tlattr)
                        # Need to set the internal representation, to allow
                        # check functions not to have to check for None.
                        setattr(self, "%s%s" % (topLevelPrepend, tlattr), None)
                        continue

                    log.debug(
                        "Generating attribute %r of %r instance", tlattr,
                        clname)
                    gen = tlad[dck.gen]
                    if isinstance(gen, str):
                        genAttr = getattr(self.__class__, gen)
                        if isinstance(genAttr, Callable):
                            log.debug(
                                "Calling callable generator attribute %r",
                                genAttr)
                            tlval = genAttr()
                        else:
                            tlval = genAttr
                    else:
                        tlval = gen(**tlsvals)

                log.detail(
                    "Set %r attribute %r to %r", clname,
                    tlattr, tlval)
                setattr(self, tlattr, tlval)

            log.detail("Dict before dele attributes: %r", sd)
            for deleAttr, deleVal in iteritems(dele_attrs):
                log.debug("Set delegate attribute %r", deleAttr)
                setattr(self, deleAttr, deleVal)

            log.detail("Final dict: %r", sd)

        def _dc_kvReprGen(self):
            for attr in iterkeys(topLevelAttributeDescs):
                yield "%s=%r" % (attr, getattr(self, attr))
            return
            sp = super(DeepClass, self)
            if hasattr(sp, "_dc_kvReprGen"):
                for kvp in sp._dc_kvReprGen():
                    yield kvp

        def __repr__(self):
            return("%s(%s)" % (
                self.__class__.__name__, ", ".join(self._dc_kvReprGen())))

    return DeepClass
