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
from collections import Callable, OrderedDict
from contextlib import contextmanager
from copy import deepcopy
import logging
from six import (iteritems, iterkeys)
from six.moves import intern
from .util import (
    append_to_exception_message, CheckingProperty, Enum, DerivedProperty,
    profile)
from .vb import ValueBinder

log = logging.getLogger(__name__)
enable_debug_logs = False

DeepClassKeys = Enum(("check", "get", "set", "gen", "descriptor",))
dck = DeepClassKeys

# Since we're going to be using these a lot it's actually a lot more efficient
# to cache them here...
gen_key = dck.gen

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

    _in_repr_attr_name = intern('_'.join(('', topLevelPrepend, 'in_repr')))

    # When we come to initialize the top level attributes, we need to do the
    # non descriptors first, and so separate them out here so that we don't
    # have to do it on the fly each time we create a DeepClass instance.
    _tlad_no_descriptors = {
        key: val
        for key, val in iteritems(topLevelAttributeDescs)
        if dck.descriptor not in val
    }
    _tlad_descriptors = {
        key: val
        for key, val in iteritems(topLevelAttributeDescs)
        if dck.descriptor in val
    }

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

        @profile
        def __init__(self, **kwargs):
            """Initialize a deepclass instance.

            Note that this method is HIGHLY performance critical, and as such
            detail logging is switched out locally rather than even using the
            global splogging disable switch. Various other parts are optimized
            too so modify at your peril.
            """
            enable_debug_logs and log.detail(
                "DeepClass %r init with kwargs: %r", type(self).__name__,
                kwargs)

            # Preload the top level attributes dictionary and our instance
            # dictionary.
            #
            # 20160904 DMP: tried optimizing by pre-generating these and using
            # deepcopy and also using two dictionary comprehensions, but no
            # perf improvement.
            topLevelAttrArgs = OrderedDict()
            self.__dict__[_in_repr_attr_name] = False
            for tl_name in iterkeys(_tlad_no_descriptors):
                self.__dict__[topLevelPrepend + tl_name] = None
                topLevelAttrArgs[tl_name] = [None, {}]

            for tl_name in iterkeys(_tlad_descriptors):
                self.__dict__[topLevelPrepend + tl_name] = None
                topLevelAttrArgs[tl_name] = [None, {}]

            enable_debug_logs and log.detail("Start dict: %r", self.__dict__)

            if kwargs:
                # As a very small optimization only do this if we have kwargs.
                superKwargs, dele_attrs = self._dck_filter_super_kwargs(
                    kwargs, topLevelAttrArgs, topLevelAttributeDescs)
            else:
                dele_attrs = superKwargs = {}

            # Call super init.
            enable_debug_logs and log.detail(
                "super init dict: %r", superKwargs)
            try:
                super(DeepClass, self).__init__(**superKwargs)
            except TypeError as terr:
                if 'takes no parameters' in str(terr):
                    append_to_exception_message(
                        terr,
                        ' - kwargs remaining were %s' % (superKwargs,))
                    raise
                raise

            # Initialize the attributes, but notice that topLevelAttrArgs has
            # been pre-ordered to have the descriptor attributes last, in case
            # any descriptor attributes depend on normal ones.
            for tlattr, (tlval, tlsvals) in iteritems(topLevelAttrArgs):
                tlad = topLevelAttributeDescs[tlattr]

                if tlval is None:
                    tlattr_val = getattr(self, tlattr, None)
                    if tlattr_val is not None:
                        enable_debug_logs and log.debug(
                            "No need to generate %r for %r: already "
                            "set (probably by bindings) to %r.",
                            tlattr, type(self).__name__, tlattr_val)
                        continue

                    genner = tlad.get(gen_key)
                    if genner is None:
                        enable_debug_logs and log.debug(
                            "%r attribute not set and doesn't have "
                            "generator",
                            tlattr)
                        # Need to set the internal representation, to allow
                        # check functions not to have to check for None.
                        setattr(
                            self, str(topLevelPrepend) + str(tlattr), None)
                        continue

                    enable_debug_logs and log.debug(
                        "Generating attribute %r of %r instance", tlattr,
                        type(self).__name__)
                    tlval = self._dck_genTopLevelValueFromTLDict(
                        genner, tlad, tlsvals)

                enable_debug_logs and log.detail(
                    "Set %r attribute %r to %r", type(self).__name__,
                    tlattr, tlval)
                setattr(self, tlattr, tlval)

            enable_debug_logs and log.detail(
                "Dict before dele attributes: %r", self.__dict__)
            for deleAttr, deleVal in iteritems(dele_attrs):
                enable_debug_logs and log.debug(
                    "Set delegate attribute %r", deleAttr)
                setattr(self, deleAttr, deleVal)

            enable_debug_logs and log.detail("Final dict: %r", self.__dict__)

        def _dc_kvReprGen(self):
            for attr in iterkeys(topLevelAttributeDescs):
                yield "%s=%r" % (attr, getattr(self, attr))
            return

        def _dck_genTopLevelValueFromTLDict(self, gen, tlad, tlsvals):
            if isinstance(gen, str):
                genAttr = getattr(type(self), gen)
                if isinstance(genAttr, Callable):
                    log.debug(
                        "Calling callable generator attribute %r", genAttr)
                    return genAttr()

                return genAttr

            try:
                return gen(**tlsvals)
            except Exception as exc:
                append_to_exception_message(
                    exc, ' - processing constructor %s' % gen)
                raise

        @contextmanager
        def _dc_enter_repr(self):
            setattr(self, _in_repr_attr_name, True)
            try:
                yield
            finally:
                setattr(self, _in_repr_attr_name, False)

        def _dck_filter_super_kwargs(self, kwargs, topLevelAttrArgs,
                                     topLevelAttributeDescs):
            """Deduce kwargs that need to be passed to super.

            Starting with::

                kwargs = {"topLevelAttribute__tlaSubAttribute1": subValue,
                          "topLevelAttribute": value,
                          "super_attribute": super_value,
                          "vb_delegated_attribute": del_value}

            End with::

                topLevelAttrArgs = {
                    "topLevelAttribute": [
                        value,  # May be None.
                        {
                           "tlaSubAttribute1": subValue,
                        }
                    ]
                }

            and return::

                {"super_attribute": super_value},
                {"vb_delegated_attribute": del_value}

            """
            superKwargs = {}
            dele_attrs = {}
            vbds = getattr(self, '_vb_delegate_attributes', {})

            for kwName, kwVal in iteritems(kwargs):
                topLevelAttrName, _, subAttr = kwName.partition("__")
                desc = topLevelAttributeDescs.get(topLevelAttrName)
                if desc is None:
                    if topLevelAttrName not in vbds:
                        enable_debug_logs and log.detail(
                            "Super kwarg %r", kwName)
                        superKwargs[kwName] = kwVal
                        continue

                    # Got a delegate attribute
                    dele_attrs[kwName] = kwVal
                    continue

                enable_debug_logs and log.detail(
                    "Deep class kwarg %r %r", kwName, kwVal)
                tlaa = topLevelAttrArgs[topLevelAttrName]

                if len(_) != 0:
                    if len(subAttr) == 0:
                        raise KeyError(
                            "Attribute %r of %r instance not a valid "
                            "subattribute of attribute %r." % (
                                kwName, type(self).__name__,
                                topLevelAttrName))
                    tlaa[1][subAttr] = kwVal
                else:
                    tlaa[0] = kwVal
            return superKwargs, dele_attrs

        def __repr__(self):
            if getattr(self, _in_repr_attr_name):
                return '<DC %x>' % id(self)

            with self._dc_enter_repr():
                myattrs = [attr_line for attr_line in self._dc_kvReprGen()]
                if (recurse_repr and
                        hasattr(super(DeepClass, self), '_dc_kvReprGen')):

                    myattrs.extend([
                        sattr
                        for sattr in super(DeepClass, self)._dc_kvReprGen()])

            return("%s(%s)" % (type(self).__name__, ", ".join(myattrs)))

        def __deepcopy__(self, memo):

            cls = type(self)
            kwargs = {
                attr: deepcopy(getattr(self, attr))
                for attr in topLevelAttributeDescs}
            log.debug('deepcopy %s instance: %r', cls.__name__, kwargs)
            return cls(**kwargs)

    return DeepClass
