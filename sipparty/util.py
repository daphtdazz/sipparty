"""util.py

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
from __future__ import absolute_import

from abc import (ABCMeta, abstractmethod)
from collections import (Callable, Sequence)
import logging
import os
from six import (
    add_metaclass, binary_type as bytes, iteritems, itervalues, PY2)
from threading import currentThread
import time
import timeit
from traceback import extract_stack
from weakref import (ref as weakref, WeakValueDictionary)

from .classmaker import classmaker

log = logging.getLogger(__name__)

try:
    profile = profile
except NameError:
    def profile(func):
        return func

# The clock. Defined here so that it can be overridden in the testbed.
Clock = timeit.default_timer

# Global debug logging switch, for perf-sensitive functions.
enable_debug_logs = False


def append_to_exception_message(exc, message):
    exc_str = str(exc)
    exc_str += message
    exc.args = (exc_str,) + tuple(exc.args[1:])


class attributesubclassgen(type):  # noqa
    """This is used as a metaclass to give automatic subclass creation from
    attribute access.

    So for example:

    @add_metaclass(attributesubclassgen)
    class AttributeGen(object):

        types = Enum(("Subclass",))

    class SubclassAttributeGen(object):
        pass

    inst = AttributeGen.Subclass()

    >>> inst is an instance of Subclass.
    """

    @staticmethod
    def NormalizeGeneratingAttributeName(name):
        return name.title().replace("-", "_")

    def __init__(self, name, bases, dict):
        """__init__ for classes is called after the bases and dict have been
        set up, so no need to re-set up here."""
        log.debug("Init %r, %r, %r, %r", self.__name__, name, bases, dict)
        self._supername = name
        self._ascg_subClasses = {}
        super(attributesubclassgen, self).__init__(name, bases, dict)

    def addSubclassesFromDict(self, subclass_dict):
        superName = self._supername
        for name, obj in iteritems(subclass_dict):
            subClassType, sep, empty = name.partition(superName)
            if sep != superName or empty != '':
                continue

            log.debug("Found subclass type %r.", subClassType)
            self._ascg_subClasses[subClassType] = obj

    def __getattr__(self, name):

        if name == 'types':
            sp = super(attributesubclassgen, self)
            gt = getattr(sp, '__getattr__', None)
            if gt is not None:
                return gt(name)

            raise AttributeError(
                '%r class has no attribute \'types\'.', self.__name__)

        if hasattr(self, 'types'):
            tps = self.types
            try:
                name = getattr(tps, name)
            except AttributeError:
                log.debug(
                    "%r not a type of %r (supername %r).", name, self.__name__,
                    self._supername)
                raise

        normalizedSCType = self.NormalizeGeneratingAttributeName(name)
        log.debug("Normalized: %r -> %r.", name, normalizedSCType)
        scs = self._ascg_subClasses
        if normalizedSCType not in scs:
            log.debug(
                "No predefined to find subclass of %r of type %r.",
                self.__name__, name)

            return type(
                normalizedSCType + self._supername, (self,),
                dict())
        ty = scs[normalizedSCType]
        log.debug("Return %r for type %r from %r", ty, name, scs)
        return ty


def sipheader(key):
    """Normalizer for SIP headers, which is almost title but not quite."""
    global sipheaderreplacements
    if 'sipheaderreplacements' not in globals():
        sipheaderreplacements = {
            b'Call-Id': b'Call-ID',
            b'Www-Authenticate': b'WWW-Authenticate',
            b'Cseq': b'CSeq',
            b'Mime-Version': b'MIME-Version'
        }
        if not PY2:
            for wrong, right in iteritems(dict(sipheaderreplacements)):
                sipheaderreplacements[astr(wrong)] = astr(right)

    nk = key.title()
    if isinstance(key, str):
        nk = nk.replace("_", "-")
    else:
        nk = nk.replace(b'_', b'-')

    if nk in sipheaderreplacements:
        nk = sipheaderreplacements[nk]

    return nk


class Enum(set):
    """This enum is ordered, and indexes of objects can be looked up, as well
    as having attributes and having set behaviour and optional normalization.
    It composes with a list to implement the listy bits.
    """

    def __init__(self, vals=None, normalize=None, aliases=None):
        self._en_normalize = normalize
        self._en_aliases = aliases

        vlist = [] if not vals else list(vals)

        if aliases:
            for v in itervalues(aliases):
                if v not in vlist:
                    vlist.append(v)

        super(Enum, self).__init__(vlist)
        self._en_list = vlist

    def __or__(self, other):
        return Enum(set(self) | set(other))

    def __contains__(self, name):
        """Look up an Enum value using subscript access.

        See perf comments for `__getattr__`.
        """
        if super(Enum, self).__contains__(name):
            return True

        nn = self._en_fixAttr(name)
        return super(Enum, self).__contains__(nn)

    def __getattr__(self, attr):
        """Do a lookup of the value in the Enum using attribute access.

        This is highly perf sensitive, and in particular is optimized for
        the default case where there is no need to fix up the attribute (where
        the programmer has hard-coded the value).
        """
        if super(Enum, self).__contains__(attr):
            return attr

        # The raw value was not a member of the enum, so try fixing up.
        nn = self._en_fixAttr(attr)
        if super(Enum, self).__contains__(nn):
            return nn
        raise AttributeError("Attribute %r not one of %r." % (nn, self))

    def __iter__(self):
        return self._en_list.__iter__()

    def __getitem__(self, index):
        return self._en_list.__getitem__(index)

    def index(self, item):
        return self._en_list.index(item)

    def add(self, item):

        super(Enum, self).add(item)
        ll = self._en_list
        if item not in ll:
            ll.append(item)

    def update(self, iterable):
        for item in iterable:
            self.add(item)

    def REPattern(self):
        return "(?:%s)" % "|".join(self)

    def enum(self):
        return self

    def _en_fixAttr(self, name):
        if self._en_aliases:
            enable_debug_logs and log.detail('Is %r is an alias', name)
            if name in self._en_aliases:
                val = self._en_aliases[name]
                enable_debug_logs and log.debug(
                    '%r is an alias to %r', name, val)
                return val

        if self._en_normalize:
            return self._en_normalize(name)

        return name


if not PY2:
    class AsciiBytesEnum(Enum):

        def __init__(self, vals=None, normalize=None, aliases=None):
            def bad_val_type(val):
                raise TypeError(
                    '%r instance %r cannot be used in %r instance as it is '
                    'not a bytes-like type.' % (
                        val.__class__.__name__, val, self.__class__.__name__))

            if vals:
                for vv in [
                        _vv
                        for _vl in (vals, aliases) if _vl is not None
                        for _vv in _vl]:
                    if not isinstance(vv, bytes):
                        bad_val_type(vv)
            super(AsciiBytesEnum, self).__init__(
                vals=vals, normalize=normalize, aliases=aliases)

        def add(self, item):
            if not isinstance(item, bytes):
                raise TypeError(
                    'New %r instance is inconsistent with enum %r containing '
                    'only instances of %r' % (
                        item.__class__.__name__, self, self._en_type.__name__))
            super(AsciiBytesEnum, self).add(item)

        def REPattern(self):
            return b"(?:%s)" % b"|".join(self)

        def enum(self):
            return Enum(
                [astr(val) for val in self._en_list],
                aliases=self._en_aliases, normalize=self._en_normalize)

        def _en_fixAttr(self, name):
            if isinstance(name, str):
                log.detail('Convert %r to ascii bytes', name)
                name = abytes(name)

            fixedStrAttr = super(AsciiBytesEnum, self)._en_fixAttr(name)
            return fixedStrAttr

else:
    AsciiBytesEnum = Enum


class ClassType(object):
    """Dynamic property that returns a string naming the "type" of the
    instance. This is the class name with {self.class_append} removed.
    """

    def __init__(self, class_append):
        self.class_append = class_append
        self.__doc__ = self.__doc__.format(**locals())

    def __get__(self, instance, owner):
        """This is optimized for performance as it is hit frequently."""
        try:
            return getattr(
                owner.types,
                owner.__name__.replace(self.class_append, '')
            )
        except AttributeError:
            raise AttributeError(
                "No such known header class type %r" % (
                    owner.__name__.replace(self.class_append, ''),))


class FirstListItemProxy(object):
    """This descriptor provides access to the first item in a list attribute.
    """

    def __init__(self, list_attr_name):
        """
        :param str list_attr_name: Should be the name of an attribute.
        """
        super(FirstListItemProxy, self).__init__()

        if not isinstance(list_attr_name, str):
            raise TypeError(
                'List attribute name passed to FirstListItemProxy is not a '
                'string: %r' % list_attr_name)

        try:
            hasattr(self, list_attr_name)
        except TypeError:
            raise TypeError(
                "list_attr_name {0} wrong type.".format(list_attr_name))

        self._flip_attrName = list_attr_name

    def __get__(self, instance, owner):
        """
        If the instance has the attribute, or it is None or an empty
        Sequence, getting this descriptor will raise AttributeError, as the
        instance clearly doesn't have a 'first list item' to get.

        If the instance has this attribute and it is a non-empty Sequence, then
        the first item of the Sequence is returned.

        Otherwise raises TypeError.
        """

        if instance is None:
            return owner

        list_attr = getattr(instance, self._flip_attrName)

        def attr_err():
            raise AttributeError(
                "Instance %r of class %r does not have attribute %r." % (
                    instance, owner, self._flip_attrName))

        if list_attr is None:
            attr_err()

        if not isinstance(list_attr, Sequence):
            raise TypeError(
                'List attribute %r of %r instance is not a Sequence (has type '
                '%r) and cannot be used with FirstListItemProxy' % (
                    self._flip_attrName, instance.__class__.__name__,
                    list_attr.__class__.__name__))

        for obj in list_attr:
            # I.e. just return the first item, if the list is not empty.
            return obj

        # List was empty, raise AttributeError.
        attr_err()

    def __set__(self, instance, val):

        # Use a slice which works for the first addition as well.
        list_attr = getattr(instance, self._flip_attrName)
        list_attr[0:1] = (val,)


class GenerateIfNotSet(object):
    def __init__(self, attrname, alwaysregen=False):
        self.attrname = attrname
        self._gins_generator_name = "generate_%s" % attrname
        self._gins_always_regen = alwaysregen

    def __get__(self, instance, owner):
        log.debug("%r instance get %r", owner.__name__, self.attrname)
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute {1!r}".format(
                    owner.__name__, self.attrname))

        if (self._gins_always_regen or
                self.attrname not in instance.__dict__ or
                instance.__dict__[self.attrname] is None):
            if not hasattr(instance, self._gins_generator_name):
                msg = (
                    "{instance.__class__.__name__!r} instance wants to "
                    "generate attribute {self.attrname!r} but has no "
                    "generator method {self._gins_generator_name!r}"
                    "".format(**locals()))
                log.debug(msg)
                raise AttributeError(msg)

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

    if isinstance(props, str):
        props = (props,)

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

            dummy_class = classmaker()(dprefix + name, bases, {})
            mro = dummy_class.__mro__

            log.debug("Class dictionary: %r.", class_dict)
            log.debug("Accumulate properties %r of %r.", props, name)
            for cprop_name in props:

                newcprops = None
                method = None

                def bdgen():
                    for b in mro[-1:0:-1]:
                        yield b.__dict__
                    yield class_dict
                for base_dict in bdgen():
                    if cprop_name not in base_dict:
                        continue

                    if newcprops is None:
                        # Found first property to accumulate; deduce the type.
                        cpt = type(base_dict[cprop_name])
                        log.debug(
                            "%r property is of type %r.", cprop_name,
                            cpt.__name__)
                        newcprops = cpt()

                        # Use update if it has it.
                        if hasattr(newcprops, "update"):
                            method = getattr(newcprops, "update")
                        elif hasattr(newcprops, "append"):
                            def update_from_extend(new_vals):
                                log.debug(
                                    "Append to %r %r", newcprops, new_vals)
                                for val in new_vals:
                                    if val in newcprops:
                                        continue
                                    newcprops.append(val)

                            method = update_from_extend
                        else:
                            raise AttributeError(
                                "Cumulative property {cprop_name!r} is "
                                "neither appendable nor updatable."
                                "".format(**locals()))
                    assert method is not None
                    inh_cprops = base_dict[cprop_name]
                    log.debug("Run method on %r", inh_cprops)
                    method(inh_cprops)

                if newcprops is None:
                    raise ValueError(
                        "Cumulative property %r doesn't exist in class %r or "
                        "its superclasses." % (cprop_name, name))

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


class class_or_instance_method(object):  # noqa
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


def OnlyWhenLocked(method, allow_recursion=False):
    """This decorator sees if the owner of method has a _lock attribute, and
    if so locks it before calling method, releasing it after."""

    def maybeGetLock(self, *args, **kwargs):
        """Get the method object's lock and call the method with it.

        This function is performance critical.
        """
        cthr = currentThread()
        if cthr is self._lock_holdingThread:
            if allow_recursion:
                return method(self, *args, **kwargs)

            raise RuntimeError(
                "Thread %s attempting to get FSM lock when it already has "
                "it." % cthr.name)

        # We needed the lock and we have it.
        with self._lock:
            self._lock_holdingThread = cthr
            try:
                return method(self, *args, **kwargs)
            finally:
                self._lock_holdingThread = None

    return maybeGetLock


class CheckingProperty(object):

    def __init__(self, *args, **kwargs):
        self.check = kwargs.pop('check', None)
        args = list(args)
        if len(args) > 0:
            name = args.pop(0)
        else:
            name = kwargs.pop('name')
        self.__name = name
        super(CheckingProperty, self).__init__(name, *args, **kwargs)

    def __set__(self, obj, value):
        check = self.check
        if value is not None and check is not None:
            exc_type = None
            try:
                if not check(value):
                    raise ValueError()
            except (ValueError, TypeError) as exc:
                exc_type = type(exc)
                exc_class = (
                    ValueError if issubclass(exc_type, ValueError) else
                    TypeError)
            finally:
                if exc_type is not None:
                    raise exc_class(
                        "%r instance %r is not an allowed value for attribute "
                        "%s of class %r." % (
                            type(value).__name__, value,
                            self.__name, type(obj).__name__))

        super(CheckingProperty, self).__set__(obj, value)


class _DerivedProperty(object):

    def update(self, new_derived_property):
        """Updates the derived property so that subclasses can override
        particular methods.

        :param new_derived_property: an instance of `DerivedProperty`.
        """
        log.debug("Update %r with %r.", self, new_derived_property)
        for pr in ("_rp_propName", "_rp_get", "_rp_set", "_rp_check"):
            np = getattr(new_derived_property, pr)
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
        log.detail("%r", self)

    def __get__(self, obj, cls):
        target = obj if obj is not None else cls
        val = getattr(target, self._rp_propName)

        gt = self._rp_get
        if gt is None:
            # No getter, so return now.
            return val

        # Get might be a method name...
        if isinstance(gt, str):
            meth = getattr(target, gt, None)
            if not isinstance(meth, Callable):
                raise ValueError(
                    "Getter attribute %r of %r object is not callable." % (
                        gt, type(target).__name__))
            return meth(val)

        # Else getter should be a callable.
        if not isinstance(gt, Callable):
            raise ValueError(
                "Getter %r object for DerivedValue on %r on %r object is not "
                "a callable or a method name." % (
                    gt, self._rp_propName, type(target).__name__))
        val = gt(obj, val)
        return val

    def __set__(self, obj, value):
        pname = self._rp_propName

        st = self._rp_set

        if st is None:
            log.debug("Set %r to %r.", pname, value)
            log.debug("Self: %r.", self)
            setattr(obj, pname, value)
        elif isinstance(st, str):
            meth = getattr(obj, st, None)
            if not isinstance(meth, Callable):
                raise ValueError(
                    "Setter attribute %r of %r object is not callable." % (
                        st, obj.__class__.__name__))
            meth(value)
        else:
            st(obj, value)

    def __delete__(self, obj):
        pname = self._rp_propName
        delattr(obj, pname)

    def __repr__(self):
        return (
            "DerivedProperty({_rp_propName!r}, check={_rp_check!r}, "
            "get={_rp_get!r}, set={_rp_set!r})"
            "".format(**self.__dict__))


DerivedProperty = type(
    'DerivedProperty', (CheckingProperty, _DerivedProperty), {})


def TwoCompatibleThree(cls):
    """Class decorator that makes certain python 3 aspects of the class
    compatible with python 2.

    These are:
        __bytes__  - is called instead of __str__ in python 2."""
    if PY2:
        class BytesToStrDescriptor(object):
            def __get__(self, obj, cls):
                return (
                    obj.__bytes__ if obj is not None
                    else cls.__bytes__)

        cls.__str__ = BytesToStrDescriptor()

    return cls


def WeakMethod(object, method, static_args=None, static_kwargs=None,
               default_rc=None):
    wr = weakref(object)

    static_args = static_args if static_args is not None else []
    static_kwargs = static_kwargs if static_kwargs is not None else {}

    def weak_method(*args, **kwargs):
        log.debug("static_args: %r", static_args)
        log.debug("args: %r", args)
        sr = wr()
        if sr is None:
            log.warning(
                'Method %s cannot be called as its object has been released.',
                method)
            return default_rc

        pass_args = (list(static_args) + list(args))
        log.debug("pass_args: %r", pass_args)
        pass_kwargs = dict(static_kwargs)
        pass_kwargs.update(kwargs)
        log.info('Call method %s of %s instance', method, type(sr).__name__)
        return getattr(sr, method)(*pass_args, **pass_kwargs)

    return weak_method


class Timeout(Exception):
    pass


def WaitFor(
    condition, timeout_s=None, action_on_timeout=None, resolution=0.0001,
    action_each_cycle=None
):
    if timeout_s is None:
        timeout_s = int(os.environ.get('PYTHON_WAITFOR_TIMEOUT', 1.0))

    now = Clock()
    next_log = now + 1
    until = now + timeout_s
    while now < until:
        now = Clock()
        if now > next_log:
            next_log = Clock() + 1
            log.debug("Still waiting for %r...", condition)

        if action_each_cycle is not None:
            action_each_cycle()
        if condition():
            break
        time.sleep(resolution)

    else:
        if action_on_timeout:
            action_on_timeout()
        else:
            raise Timeout("Timed out (after %g seconds) waiting for %r" % (
                float(timeout_s), condition)
            )


class SingletonType(type):

    # Dictionary of names. This is to prevent double __new__.
    __instance_names = {}

    @property
    def __initing_attribute(self):
        return '__' + self.__name__ + '_singleton_initing'

    def __new__(cls, name, bases, dct):

        log.debug(
            'New %r instance called %r with bases %r', cls.__name__, name,
            bases)
        init_proc = dct.get('__init__', None)
        new_module_name = []

        # Create a wrapper for the init. This is to prevent the init of the
        # underlying class from being called twice.
        def singleton_init_wrapper(self, singleton=None, *args, **kwargs):

            assert len(new_module_name) == 1
            singleton_subclass = cls.__instance_names[new_module_name[0]]
            log.debug(
                'Init of %r type wrapper for %r instance, initing attr %r',
                singleton_subclass.__name__,
                self.__class__.__name__,
                singleton_subclass.__initing_attribute)

            if hasattr(self, 'singleton_inited'):
                log.debug('  instance already inited')
                return

            ia = singleton_subclass.__initing_attribute
            try:
                if not getattr(self, ia, False) and init_proc is not None:
                    log.debug(
                        'Call underlying init method %r on %r class',
                        init_proc, singleton_subclass.__name__)
                    setattr(self, ia, True)
                    init_proc(self, *args, **kwargs)
                else:
                    # This class didn't have an init proc, so recurse to the
                    # next one in the mro.
                    setattr(self, ia, True)
                    try:
                        assert isinstance(self, object)
                        assert not isinstance(self, type)
                        assert isinstance(singleton_subclass, type)
                        assert singleton_subclass in self.__class__.__mro__, (
                            singleton_subclass, id(singleton_subclass),
                            self.__class__.__mro__,
                            [id(base) for base in self.__class__.__mro__],
                            singleton_subclass.__module__ + '.' +
                            singleton_subclass.__name__)
                        log.debug(
                            'Call super(%r, %r).init', singleton_subclass,
                            self)
                        super(singleton_subclass, self).__init__(
                            *args, **kwargs)
                    except:
                        log.warning(
                            'super init failed on %r, wrapper for '
                            '%r',
                            self, singleton_subclass)
                        raise

                self.singleton_inited = True
            finally:
                setattr(self, singleton_subclass.__initing_attribute, False)

        dct['__init__'] = singleton_init_wrapper

        # Now we've patched init, we can call super to create the instance of
        # this metaclass.
        new_type = super(SingletonType, cls).__new__(
            cls, name, bases, dct)

        module_path = '.'.join((new_type.__module__, new_type.__name__))
        new_module_name.append(module_path)

        if module_path in cls.__instance_names:
            log.debug(
                'Overwriting existing class at %s, check this is using the '
                'six module', module_path)
            st = extract_stack()
            for frame in st[::-1]:
                if 'six.py' in frame[0] and 'wrapper' in frame[2]:
                    break
            else:
                raise RuntimeError(
                    'Unexpected double creation of type %s inheriting from '
                    '\'singleton.Singleton\'. Creating two types with the '
                    'same name in the same module that both inherit from '
                    'Singleton is not supported.' % module_path)

        cls.__instance_names[module_path] = new_type

        log.debug('New %r instance %s - FINISHED', cls.__name__, module_path)
        return new_type


@add_metaclass(SingletonType)
class Singleton(object):
    """Classes inheriting from this will only have one instance."""

    UseStrongReferences = False
    _St_SharedInstances = None

    @classmethod
    def wait_for_no_instances(cls, **kwargs):
        assert not cls.UseStrongReferences

        # We only want any instances for this particular class, not
        # superclasses.
        si = cls.__dict__.get('_St_SharedInstances')
        if si is None:
            return
        try:
            WaitFor(lambda: all(wr is None for wr in si.values()), **kwargs)
        except Timeout:
            raise Timeout(
                'Timed out waiting for no instances of Singleton class %s' % (
                    cls.__name__,))

    def __new__(cls, singleton=None, *args, **kwargs):
        log.detail("Singleton.__new__(%r, %r)", args, kwargs)
        if singleton is not None:
            name = singleton
        else:
            name = cls.__name__

        log.debug("Get singleton for class %r, name %r", cls, name)

        insts = cls._St_SharedInstances
        if insts is None:
            if cls.UseStrongReferences:
                insts = {}
            else:
                insts = WeakValueDictionary()
            cls._St_SharedInstances = insts

        existing_inst = insts.get(name, None)

        if existing_inst is not None:
            log.debug("Return Existing instance")
            log.detail("%r", existing_inst)
            return existing_inst

        try:
            ni = super(Singleton, cls).__new__(cls)
        except TypeError:
            log.error('args: %s; kwargs: %s', args, kwargs)
            raise
        log.info(
            "New Singleton subclass %s instance called '%s' created",
            cls.__name__, name)

        insts[name] = ni
        ni.singleton_name = name
        return ni


@add_metaclass(ABCMeta)
class TupleRepresentable(object):
    """Semi-abstract base class for objects that can be represented
    by Tuples, providing equality and hash function."""

    #
    # =================== ABC INTERFACE =======================================
    #
    @abstractmethod
    def tupleRepr(self):
        raise AttributeError(
            "%r needs to implement 'tupleRepr' itself to inherit from "
            "TupleRepresentable" % (self.__class__.__name__,))

    #
    # =================== INTERNAL METHODS ====================================
    #
    def __get_check_tuple_repr(self):
        mytr = self.tupleRepr()
        if not isinstance(mytr, tuple):
            raise TypeError(
                '%r instance tupleRepr method returned a value that was not a '
                'tuple: %r' % (self.__class__.__name__, mytr))
        return mytr

    #
    # =================== MAGIC METHODS =======================================
    #
    def __repr__(self):
        return "%s%r" % (self.__class__.__name__, self.tupleRepr())

    def __eq__(self, other):
        if not isinstance(other, TupleRepresentable):
            return False
        mytr = self.__get_check_tuple_repr()
        return mytr == other.tupleRepr()

    def __hash__(self):
        return hash(self.__get_check_tuple_repr())


@TwoCompatibleThree
class BytesGenner(object):

    def bytesGen(self):
        raise AttributeError(
            "%r class has not overridden 'bytesGen' which is required to "
            "inherit from BytesGenner" % (self.__class__.__name__,))

    def safeBytesGen(self):
        for bb in self.bytesGen():
            log.detail('Next bytes %r', bb)
            if not isinstance(bb, bytes):
                raise TypeError(
                    '%r instance generated un-bytes-like object %r' % (
                        self.__class__.__name__, bb))
            yield bb

    def __bytes__(self):
        log.detail(
            'Generating bytes for BytesGenner subclass %r',
            type(self).__name__)
        return b''.join(self.safeBytesGen())


def bglobals_g(gbls):
    bglobals = {}

    for key, val in iteritems(gbls):
        if key.startswith('_'):
            continue

        if isinstance(val, bytes):
            bglobals[abytes(key)] = val

        elif isinstance(val, AsciiBytesEnum):
            for enum_val in val:
                bglobals[b'%s.%s' % (abytes(key), enum_val)] = enum_val

        elif isinstance(val, Enum):
            for enum_val in val:
                bglobals['%s.%s' % (key, enum_val)] = enum_val

        else:
            bglobals[key] = val

    return bglobals


if PY2:
    def abytes(x):
        return x
    astr = abytes
else:
    def abytes(x):
        if x is None:
            return None
        if isinstance(x, bytes):
            return x
        try:
            return bytes(x, encoding='ascii')
        except TypeError as exc:
            raise type(exc)(
                'Bad type %r for argument %r to abytes (not str).' % (
                    type(x).__name__, x))

    def astr(x):
        if x is None:
            return None
        if isinstance(x, str):
            return x
        return str(x, encoding='ascii')


class DelegateProperty(object):

    _sentinel = type('DelegatePropertySentinel', (), {})()

    def __init__(self, delegate_attribute, attribute):
        self.__delegate_attribute = delegate_attribute
        self.__attribute = attribute

    def __get__(self, obj, cls):
        if obj is None:
            return self

        delegate = getattr(obj, self.__delegate_attribute, self._sentinel)
        if delegate is self._sentinel:
            raise AttributeError(
                '%r has no delegate at %r.', obj, self.__delegate_attribute)

        val = getattr(delegate, self.__attribute, self._sentinel)
        if val is self._sentinel:
            raise AttributeError(
                '%r delegate %r at attribute %r has no attribute %r', obj,
                delegate, self.__delegate_attribute, self.__attribute)

        return val

    def __set__(self, obj, val):

        delegate = getattr(obj, self.__delegate_attribute, self._sentinel)
        if delegate is self._sentinel:
            raise AttributeError(
                '%r has no delegate at %r.', obj, self.__delegate_attribute)

        setattr(delegate, self.__attribute, val)


class Retainable(object):

    def __init__(self):
        super(Retainable, self).__init__()
        self.__retain_count = 0

    @property
    def is_retained(self):
        return self.__retain_count != 0

    def retain(self):
        self.__retain_count += 1
        log.debug('retain count now %d', self.__retain_count)

    def release(self):
        self.__retain_count -= 1
        log.debug('retain count now %d', self.__retain_count)


class WeakProperty(object):

    def __init__(self, pname):
        self.__pname = '__weakref_' + pname

    def __get__(self, obj, cls):
        if obj is None:
            return self

        wr = getattr(obj, self.__pname, None)
        if wr is None:
            return None

        return wr()

    def __set__(self, obj, val):
        wr = weakref(val)
        setattr(obj, self.__pname, wr)


class FallbackProperty(object):

    def __init__(self, pname, fallbacks):
        self._fp_prop_name = pname
        self._fp_fallbacks = fallbacks

    def __get__(self, obj, owner):
        if obj is None:
            return self

        obj_val = getattr(obj, self._fp_prop_name, None)
        if obj_val is not None:
            return obj_val

        for fallback in self._fp_fallbacks:
            if isinstance(fallback, str):
                obj_val = getattr(self, fallback, None)
                if obj_val is not None:
                    return obj_val
                continue

            raise TypeError(
                'Bad object %r used for fallback attribute' % fallback)
