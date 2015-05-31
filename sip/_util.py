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
import six
import types
import collections
import copy
import threading
import time
import timeit
import logging
import pdb
import vb
import weakref

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
bytes = six.binary_type

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
                "{cls.__name__!r} needs a 'types' attribute (getting "
                "attribute {name!r}).".format(
                    **locals()))

        # !!! Would be nice to implement "type_aliases" so that we can map
        # short names to longer names.

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

    def __init__(self, vals=None, normalize=None):
        self.normalize = normalize
        super(Enum, self).__init__(*[v for v in [vals] if v is not None])
        self._en_list = list(*[v for v in [vals] if v is not None])

    def __contains__(self, val):
        if self.normalize is not None:
            nn = self.normalize(val)
        else:
            nn = val
        rb = super(Enum, self).__contains__(nn)
        # log.debug("%r in %r: %r", nn, self, rb)
        return rb

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

    def add(self, item):
        super(Enum, self).add(item)
        self._en_list.append(item)

    def update(self, iterable):
        for item in iterable:
            self.add(item)


class ClassType(object):

    def __init__(self, class_append):
        self.class_append = class_append

    def __get__(self, instance, owner):
        if instance is None:
            return ""

        class_name = instance.__class__.__name__
        return getattr(instance.types, class_name.replace(
            self.class_append, ""))


class FirstListItemProxy(object):
    "This descriptor provides access to the first item in a list attribute."

    def __init__(self, list_attr_name):
        super(FirstListItemProxy, self).__init__()

        try:
            hasattr(self, list_attr_name)
        except TypeError:
            raise TypeError(
                "list_attr_name {0} wrong type.".format(list_attr_name))

        self._flip_attrName = list_attr_name

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError(
                "Class use of FirstListItemProxy descriptors not supported. "
                "List attribute name: %r." % (self._flip_attrName,))

        # Take a copy so the length won't change between checking it and
        # returning the first item.
        list_attr = list(getattr(instance, self._flip_attrName))

        if len(list_attr) == 0:
            raise AttributeError(
                "Instance %r of class %r does not have attribute %r."
                "".format(instance, owner, self._flip_attrName))

        return list_attr[0]

    def __set__(self, instance, val):
        if instance is None:
            raise AttributeError(
                "Class %r does not support FirstListItemProxy descriptors. "
                "List attribute name: %r." % (owner, self._flip_attrName))

        # Use a slice which works for the first addition as well.
        list_attr = getattr(instance, self._flip_attrName)
        list_attr[0:1] = (val,)


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
    """Metaclass generator.

    Returns a metaclass that can be used to accumulate properties from super
    classes in subclasses.
    """

    class CumulativeClassProperties(type):
        def __new__(cls, name, bases, class_dict):
            """Initializes the class dictionary, so that all the properties in
            props are accumulated with all the inherited properties in the
            base classes.
            """

            # So we don't have to do mro calculation ourselves, make a dummy
            # type using the bases passed in, which we will use to work out
            # mro later on, however we have to catch recursion since we are
            # the metaclass of at least one base class so will be called
            # again...
            dprefix = '_ccp_dummy_'
            if name.startswith(dprefix):
                return super(CumulativeClassProperties, cls).__new__(
                    cls, name, bases, class_dict)

            dummy_class = type(dprefix + name, bases, {})

            log.debug("Class dictionary: %r.", class_dict)
            log.debug("Accumulate properties %r of %r.", props, name)
            for cprop_name in props:
                if cprop_name not in class_dict:
                    log.debug("Class doesn't have property %r", cprop_name)
                    continue

                log.debug("Fixing %r", cprop_name)
                cprops = class_dict[cprop_name]
                log.debug("Starting properties %r", cprops)
                cpropstype = type(cprops)
                newcprops = cpropstype()

                # Use update if it has it.
                if hasattr(newcprops, "update"):
                    method = getattr(newcprops, "update")

                elif hasattr(newcprops, "append"):
                    def update_from_extend(new_vals):
                        log.debug("Append to %r %r", newcprops, new_vals)
                        for val in new_vals:
                            if val in newcprops:
                                continue
                            newcprops.append(val)

                    method = update_from_extend

                else:
                    raise AttributeError(
                        "Cumulative property {cprop_name!r} is neither "
                        "appendable nor updatable."
                        "".format(**locals()))

                mro = dummy_class.__mro__
                log.debug("MRO: %r", mro)
                for base in mro[-1:0:-1]:
                    # We are walking the mro ourselves, so we're just
                    # interested in what's in the dictionary, so don't do
                    # hasattr(). Ignore the last one which was the dummy
                    # class to help with MRO.
                    if cprop_name in base.__dict__:
                        log.debug("hasattr %r", cprop_name)
                        inh_cprops = base.__dict__[cprop_name]
                        log.debug("Run method on %r", inh_cprops)
                        method(inh_cprops)
                        log.debug("newcprops %r", newcprops)

                # Finally update with this class's version.
                method(cprops)
                class_dict[cprop_name] = newcprops
                log.debug("Ending property %r:%r", cprop_name,
                          class_dict[cprop_name])

            # We must do this at the end after modifying the dictionary, as
            # we won't be able to write to the python dict_proxy object
            # afterwards, and we don't want to replace __dict__ with a
            # different object.
            inst = super(CumulativeClassProperties, cls).__new__(
                cls, name, bases, class_dict)
            for cprop_name in props:
                if cprop_name in inst.__dict__:
                    log.debug("%r: %r.", cprop_name,
                              inst.__dict__[cprop_name])

            return inst

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

    def update(self, newDP):
        """Updates the derived property so that subclasses can override
        particular methods. newDP is an instance of `DerivedProperty`.""",
        log.debug("Update %r with %r.", self, newDP)
        for pr in ("_rp_propName", "_rp_get", "_rp_set", "_rp_check"):
            np = getattr(newDP, pr)
            if np is not None:
                # Only update if not None.
                log.debug("Update property %r with %s %r.",
                          self._rp_propName, pr, np)
                setattr(self, pr, np)

    def __init__(self, name=None, check=None, get=None, set=None):
        self._rp_propName = name
        self._rp_check = check
        self._rp_get = get
        self._rp_set = set

    def __get__(self, obj, cls):
        # log.debug("Get derived prop for obj %r class %r.", obj, cls)
        target = obj if obj is not None else cls

        log.debug("Get the underlying value (if any).")
        val = getattr(target, self._rp_propName)
        log.debug("Underlying value %r.", val)

        gt = self._rp_get
        if gt is None:
            # No getter, so return now.
            return val

        # Get might be a method name...
        if isinstance(gt, bytes) and hasattr(target, gt):
            meth = getattr(target, gt)
            if not isinstance(meth, collections.Callable):
                raise ValueError(
                    "Getter attribute %r of %r object is not callable." % (
                        gt, target.__class__.__name__))
            val = meth(val)
            return val

        # Else getter should be a callable.
        if not isinstance(gt, collections.Callable):
            raise ValueError(
                "Getter %r object for DerivedValue on %r on %r object is not "
                "a callable or a method name." % (
                    gt, self._rp_propName, target.__class__.__name__))
        val = gt(obj, val)
        return val

    def __set__(self, obj, value):
        pname = self._rp_propName
        if self._rp_check is not None and not self._rp_check(value):
            raise ValueError(
                "%r is not an allowed value for attribute %r of class %r." %
                (value, pname, obj.__class__.__name__))

        st = self._rp_set

        if st is None:
            log.debug("Set %r to %r.", pname, value)
            log.debug("Self: %r.", self)
            setattr(obj, pname, value)
        elif isinstance(st, bytes) and hasattr(obj, st):
            meth = getattr(obj, st)
            if not isinstance(meth, collections.Callable):
                raise ValueError(
                    "Setter attribute %r of %r object is not callable." % (
                        st, obj.__class__.__name__))
            val = meth(value)
        else:
            self._rp_set(obj, value)

    def __repr__(self):
        return (
            "DerivedProperty({_rp_propName!r}, check={_rp_check!r}, "
            "get={_rp_get!r}, set={_rp_set!r})"
            "".format(**self.__dict__))


def TwoCompatibleThree(cls):
    """Class decorator that makes certain python 3 aspects of the class
    compatible with python 2.

    These are:
        __bytes__  - is called instead of __str__ in python 2."""
    if six.PY2:
        class BytesToStrDescriptor(object):
            def __get__(self, obj, cls):
                return (
                    obj.__bytes__ if obj is not None
                    else cls.__bytes__)

        cls.__str__ = BytesToStrDescriptor()

    return cls


def WeakMethod(object, method, static_args=None, static_kwargs=None,
               default_rc=None):
    wr = weakref.ref(object)

    static_args = static_args if static_args is not None else []
    static_kwargs = static_kwargs if static_kwargs is not None else {}

    def weak_method(*args, **kwargs):
        log.debug("static_args: %r", static_args)
        log.debug("args: %r", args)
        sr = wr()
        if sr is None:
            return default_rc

        pass_args = (list(static_args) + list(args))
        log.debug("pass_args: %r", pass_args)
        pass_kwargs = dict(static_kwargs)
        pass_kwargs.update(kwargs)
        return getattr(sr, method)(*pass_args, **pass_kwargs)

    return weak_method


class Timeout(Exception):
    pass


def WaitFor(condition, timeout_s, action_on_timeout=None, resolution=0.0001):
    now = Clock()
    next_log = now + 1
    until = now + timeout_s
    while now < until:
        now = Clock()
        if now > next_log:
            next_log = Clock() + 1
            log.debug("Still waiting for %r...", condition)

        if condition():
            break
        time.sleep(resolution)

    else:
        if action_on_timeout:
            action_on_timeout()
        else:
            raise Timeout("Timed out waiting for %r" % condition)
