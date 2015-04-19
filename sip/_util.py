"""_util.py

Utility functions for py-sip.

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
import types
import threading
import timeit
import logging
import pdb
import vb

log = logging.getLogger(__name__)

# The clock. Defined here so that it can be overridden in the testbed.
Clock = timeit.default_timer


class attributesubclassgen(type):
    """This is used as a metaclass to give automatic subclass creation from
    attribute access.

    So for example:

    six.add_metaclass(attributesubclassgen)
    class AttributeGen(object):

        types = Enum(("Subclass",))

    class SubclassAttributeGen(object):
        pass

    inst = AttributeGen.Subclass()

    >>> inst is an instance of Subclass.
    """

    @classmethod
    def NormalizeGeneratingAttributeName(clscls, name):
        return name.title().replace("-", "_")

    def __init__(cls, name, bases, dict):
        """__init__ for classes is called after the bases and dict have been
        set up, so no need to re-set up here."""
        cls._supername = name

    def __getattr__(cls, name):
        if "types" not in cls.__dict__:
            raise AttributeError(
                "{cls.__name__!r} needs a 'types' attribute.".format(
                    **locals()))

        if name not in cls.__dict__["types"]:
            raise AttributeError(
                "{name!r} is not a valid subtype of {cls.__name__!r}".format(
                    **locals()))

        name = getattr(cls.__dict__["types"], name)
        subclassguess = (
            cls.NormalizeGeneratingAttributeName(name) + cls._supername)
        try:
            mod = __import__(cls.__module__)
            for modname in cls.__module__.split(".")[1:]:
                mod = getattr(mod, modname)
            rclass = getattr(mod, subclassguess)
            rclass.type = name
            return rclass

        except AttributeError:
            return type(subclassguess, (cls,), dict(type=name))


def upper(key):
    """A normalizer for Enum, which uppercases the key."""
    return key.upper()


def title(key):
    """A normalizer for Enum, which titles the key (So-Like-This)."""
    return key.title()


def sipheader(key):
    """Normalizer for SIP headers, which is almost title but not quite."""
    nk = key.title()
    nk = nk.replace("_", "-")
    if nk == "Call-Id":
        nk = "Call-ID"
    elif nk == "Www-Authenticate":
        nk = "WWW-Authenticate"
    elif nk == "Cseq":
        nk = "CSeq"
    elif nk == "Mime-Version":
        nk = "MIME-Version"

    return nk


class Enum(set):
    """This enum is ordered, and indexes of objects can be looked up, as well
    as having attributes and having set behaviour and optional normalization.
    It composes with a list to implement the listy bits.
    """

    def __init__(self, vals, normalize=None):
        self.normalize = normalize
        super(Enum, self).__init__(vals)
        self._en_list = list(vals)

    def __contains__(self, val):
        if self.normalize is not None:
            nn = self.normalize(val)
        else:
            nn = val
        return super(Enum, self).__contains__(nn)

    def __getattr__(self, name):
        if self.normalize:
            nn = self.normalize(name)
        else:
            nn = name
        if nn in self:
            return nn
        raise AttributeError(nn)

    def __iter__(self):
        return self._en_list.__iter__()

    def __getitem__(self, index):
        return self._en_list.__getitem__(index)

    def index(self, item):
        return self._en_list.index(item)

    def update(self, iterable):
        super(Enum, self).update(iterable)
        for item in iterable:
            if item in self._en_list:
                continue
            self._en_list.append(item)


class ClassType(object):

    def __init__(self, class_append):
        self.class_append = class_append

    def __get__(self, instance, owner):
        if instance is None:
            return ""

        class_name = instance.__class__.__name__
        return getattr(instance.types, class_name.replace(
            self.class_append, ""))


class Value(object):
    def __get__(self, instance, owner):
        if instance is None or len(instance.values) == 0:
            raise AttributeError(
                "{0!r} does not have attribute 'value'".format(owner.__name__))

        return instance.values[0]

    def __set__(self, instance, val):
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute 'value'".format(owner.__name__))

        instance.values.insert(0, val)


class GenerateIfNotSet(object):
    def __init__(self, attrname, alwaysregen=False):
        self.attrname = attrname
        self._gins_generator_name = "generate_%s" % attrname
        self._gins_always_regen = alwaysregen

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute {1!r}".format(
                    owner.__name__, self.attrname))

        if (self._gins_always_regen or
                self.attrname not in instance.__dict__ or
                instance.__dict__[self.attrname] is None):
            if not hasattr(instance, self._gins_generator_name):
                raise AttributeError(
                    "{instance.__class__.__name__!r} instance wants to "
                    "generate attribute {self.attrname!r} but has no "
                    "generator method {self._gins_generator_name!r}")

            instance.__dict__[self.attrname] = getattr(
                instance, self._gins_generator_name)()

        return instance.__dict__[self.attrname]

    def __set__(self, instance, value):
        instance.__dict__[self.attrname] = value

    def __delete__(self, instance):
        del instance.__dict__[self.attrname]


class Resets(object):
    """This descriptor, when set, causes the attributes in resetattrs on the
    instance to be deleted."""
    def __init__(self, attr, resetattrs):
        self.attr = attr
        self._resets_attrs = resetattrs

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute {1!r}".format(
                    owner.__name__, self.attr))

        if self.attr not in instance.__dict__:
            raise AttributeError(
                "{instance.__class__.__name__!r} has no attribute "
                "{self.attr!r}")

        return instance.__dict__[self.attr]

    def __set__(self, instance, value):
        instance.__dict__[self.attr] = value
        for resetattr in self.resetattrs:
            if hasattr(instance, resetattr):
                delattr(instance, resetattr)

    def __delete__(self, instance):
        del instance.__dict__[self.attr]


def CCPropsFor(props):

    class CumulativeClassProperties(type):
        def __init__(cls, name, bases, dict):
            """Initializes the class dictionary, so that all the properties in
            props are accumulated with all the inherited properties in the
            base classes.
            """
            log.debug("Accumulate properties %r of %r.", props, name)
            for cprop_name in props:
                if cprop_name not in dict:
                    log.debug("Class doesn't have property %r", cprop_name)
                    continue

                log.debug("Fixing %r", cprop_name)
                cprops = dict[cprop_name]
                log.debug("Starting properties %r", cprops)
                cpropstype = type(cprops)
                newcprops = cpropstype(cprops)
                log.debug("cprops copy: %r", newcprops)
                for method_name in ("extend", "update"):
                    if hasattr(newcprops, method_name):
                        break
                else:
                    raise AttributeError(
                        "Cumulative property {cprop_name!r} is neither "
                        "extendable nor updatable."
                        "".format(**locals()))
                method = getattr(newcprops, method_name)
                blist = list(bases)
                log.debug("Base list: %r", blist)
                blist.reverse()
                for base in blist:
                    if hasattr(base, cprop_name):
                        log.debug("hasattr %r", cprop_name)
                        inh_cprops = getattr(base, cprop_name)
                        log.debug("base attrs: %r", inh_cprops)
                        method(inh_cprops)
                        log.debug("newcprops %r", newcprops)

                # Finally update with this class's version.
                method(cprops)
                dict[cprop_name] = newcprops
                setattr(cls, cprop_name, newcprops)
                log.debug("Ending properties %r", dict[cprop_name])

            super(CumulativeClassProperties, cls).__init__(
                name, bases, dict)

    return CumulativeClassProperties


class class_or_instance_method(object):
    """This decorator allows you to make a method act on a class or an
    instance. So:

    class MyClass(object):
        @class_or_instance_method
        def AddProperty(cls_or_self, prop, val):
            setattr(cls_or_self, prop, val)

    inst = MyClass()
    MyClass.AddProperty("a", 1)
    inst.AddProperty("b", 2)
    MyClass.a == 1  # True
    MyClass.b # raises AttributeError
    inst.a == 1  # True
    inst.b == 2  # True
    """

    def __init__(self, func):
        self._func = func

    def __get__(self, obj, cls):
        target = obj if obj is not None else cls

        def class_or_instance_wrapper(*args, **kwargs):
            return self._func(target, *args, **kwargs)

        return class_or_instance_wrapper


def OnlyWhenLocked(method):
    """This decorator sees if the owner of method has a _lock attribute, and
    if so locks it before calling method, releasing it after."""

    def maybeGetLock(self, *args, **kwargs):
        if not hasattr(self, "_lock"):
            log.debug("No locking in this object.")
            return method(self, *args, **kwargs)

        if not hasattr(self, "_lock_holdingThread"):
            raise AttributeError(
                "Object %r of type %r uses OnlyWhenLocked but has no "
                "attribute _lock_holdingThread which is required." %
                (self, self.__class__))

        cthr = threading.currentThread()
        hthr = self._lock_holdingThread

        if cthr is hthr:
            raise RuntimeError(
                "Thread %r attempting to get FSM lock when it already has "
                "it." % cthr)

        log.debug("Thread %r get FSM %r lock for %r (held by %r).",
                  cthr, self, method, hthr)

        with self._lock:
            log.debug("Thread %r got FSM %r lock for %r.",
                      cthr, self, method)
            self._lock_holdingThread = cthr
            try:
                result = method(self, *args, **kwargs)
            finally:
                self._lock_holdingThread = None

        log.debug("Thread %r released FSM %r lock.",
                  cthr, self)
        return result

    return maybeGetLock


class DerivedProperty(object):

    def __init__(self, name, check=None, get=None, set=None):
        self._rp_propName = name
        self._rp_check = check
        self._rp_get = get
        self._rp_store = set

    def __get__(self, obj, cls):
        target = obj if obj is not None else cls
        if self._rp_get is None:
            val = getattr(target, self._rp_propName)
        else:
            val = self._rp_get(obj)
        return val

    def __set__(self, obj, value):
        pname = self._rp_propName
        if self._rp_check is not None and not self._rp_check(value):
            raise ValueError(
                "%r is not an allowed value for attribute %r of class %r." %
                (value, pname, obj.__class__.__name__))

        if self._rp_store is None:
            setattr(obj, pname, value)
        else:
            self._rp_store(obj, value)
