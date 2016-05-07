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
from contextlib import contextmanager
from copy import deepcopy
import logging
from six import (iteritems, iterkeys)
from .util import (CheckingProperty, Enum, DerivedProperty)
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

        return type(
            '%sDescriptor' % (name,), (CheckingProperty, dc), {})(
                name=internalName, check=attrDesc.get('check'))

    # Remaining keys are for the derived property class, except 'gen' which is
    # used only once at init time to populate the initial value.
    dpdict = dict(attrDesc)
    for badKey in (dck.gen,):
        if badKey in dpdict:
            del dpdict[badKey]
    log.detail(
        "New derived property for %r underlying %r: with config %r", name,
        internalName, dpdict)
    return DerivedProperty(name=internalName, **dpdict)


def DeepClass(topLevelPrepend, topLevelAttributeDescs, recurse_repr=False):
    """Creates a deep class type which
    """

    def _in_repr_attr_name():
        return '_'.join(('', topLevelPrepend, 'in_repr'))

    class DeepClass(object):

        for __dc_attr_name, __dc_attr_desc_gen in iteritems(
                topLevelAttributeDescs):
            __dc_attr_desc = DCProperty(
                topLevelPrepend, __dc_attr_name, __dc_attr_desc_gen)
            if __dc_attr_desc is None:
                continue
            locals()[__dc_attr_name] = __dc_attr_desc

        # Careful that these don't become class attributes!
        del __dc_attr_desc_gen
        del __dc_attr_desc
        del __dc_attr_name

        def __init__(self, **kwargs):

            clname = self.__class__.__name__
            log.detail("DeepClass %r init with kwargs: %r", clname,
                       kwargs)

            # Preload the top level attributes dictionary and our instance
            # dictionary.
            topLevelAttrArgs = {}
            sd = self.__dict__
            sd[_in_repr_attr_name()] = False
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
            def _dck_filter_super_kwargs(kwargs, topLevelAttrArgs):
                superKwargs = dict(kwargs)

                for kwName, kwVal in iteritems(kwargs):
                    topLevelAttrName, _, subAttr = kwName.partition("__")
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
                return superKwargs

            superKwargs = _dck_filter_super_kwargs(kwargs, topLevelAttrArgs)

            # See if we have any delegates to pass to.
            def _dck_filter_vb_dependencies():
                log.debug('Check VB dependencies')
                dele_attrs = {}
                vbds = getattr(self, 'vb_dependencies', None)
                if vbds is None:
                    return dele_attrs

                if not isinstance(self, ValueBinder):
                    raise TypeError(
                        "%r instance has 'vb_dependencies' set but is not a "
                        "subclass of 'ValueBinder'" % (
                            self.__class__.__name__,))
                allDeleAttrs = set([
                    attr for _attrs in vbds for attr in _attrs[1]])
                for kwName, kwVal in iteritems(dict(superKwargs)):
                    if kwName not in allDeleAttrs:
                        continue
                    log.debug("Delegate attribute saved: %r", kwName)
                    dele_attrs[kwName] = kwVal
                    del superKwargs[kwName]
                return dele_attrs

            dele_attrs = _dck_filter_vb_dependencies()

            # Call super init.
            log.detail("super init dict: %r", superKwargs)
            try:
                super(DeepClass, self).__init__(**superKwargs)
            except TypeError as terr:
                if 'takes no parameters' in str(terr):
                    raise TypeError(
                        'Unrecognised key-word arguments passed to %r '
                        'constructor: %r' % (
                            self.__class__.__name__, list(superKwargs.keys())))
                raise

            # Do descriptor properties after other properties, as they may
            # depend on them.
            for do_descriptors in (False, True):
                # Loop through the entries for the top level attributes, and
                # generate values for anything that's missing.
                log.detail(
                    "Recurse %s to %r top level attributes: %r",
                    'doing descriptors' if do_descriptors else
                    'not doing descriptors', clname, topLevelAttrArgs)

                for tlattr, (tlval, tlsvals) in iteritems(topLevelAttrArgs):
                    tlad = topLevelAttributeDescs[tlattr]
                    desc = tlad.get(dck.descriptor, None)

                    # Don't do descriptor-based properties if not told to.
                    if not do_descriptors and desc is not None:
                        continue

                    # Don't do non-descriptor-based properties if not told to.
                    if do_descriptors and desc is None:
                        continue

                    if tlval is None:
                        tlattr_val = getattr(self, tlattr, None)
                        if tlattr_val is not None:
                            log.debug(
                                "No need to generate %r for %r: already "
                                "set (probably by bindings) to %r.",
                                tlattr, clname, tlattr_val)
                            continue

                        genner = tlad.get(dck.gen, None)
                        if genner is None:
                            log.debug(
                                "%r attribute not set and doesn't have "
                                "generator",
                                tlattr)
                            # Need to set the internal representation, to allow
                            # check functions not to have to check for None.
                            setattr(
                                self, str(topLevelPrepend) + str(tlattr), None)
                            continue

                        log.debug(
                            "Generating attribute %r of %r instance", tlattr,
                            clname)
                        tlval = self._dck_genTopLevelValueFromTLDict(
                            tlad, tlsvals)

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

        def _dck_genTopLevelValueFromTLDict(self, tlad, tlsvals):
            """:param tlad:
                The Top-Level-Attribute Dictionary, which describes
                the attribute.
            """
            gen = tlad[dck.gen]
            if isinstance(gen, str):
                genAttr = getattr(self.__class__, gen)
                if isinstance(genAttr, Callable):
                    log.debug(
                        "Calling callable generator attribute %r", genAttr)
                    return genAttr()

                return genAttr

            return gen(**tlsvals)

        @contextmanager
        def _dc_enter_repr(self):
            irat = _in_repr_attr_name()
            setattr(self, irat, True)
            try:
                yield
            finally:
                setattr(self, irat, False)

        def __repr__(self):
            if getattr(self, _in_repr_attr_name()):
                return '<DC %x>' % id(self)

            with self._dc_enter_repr():
                myattrs = [attr_line for attr_line in self._dc_kvReprGen()]
                if (recurse_repr and
                        hasattr(super(DeepClass, self), '_dc_kvReprGen')):

                    myattrs.extend([
                        sattr
                        for sattr in super(DeepClass, self)._dc_kvReprGen()])

            return("%s(%s)" % (self.__class__.__name__, ", ".join(myattrs)))

        def __deepcopy__(self, memo):

            cls = type(self)
            kwargs = {
                attr: deepcopy(getattr(self, attr))
                for attr in topLevelAttributeDescs}
            log.debug('deepcopy %s instance: %r', cls.__name__, kwargs)
            return cls(**kwargs)

    return DeepClass
