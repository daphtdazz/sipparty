"""adapter.py

Adapter design pattern implementation.

Copyright 2016 David Park

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
from abc import (abstractmethod, abstractproperty)
from collections import Mapping
import logging
from six import add_metaclass
from weakref import ref
from .util import Singleton
from ._adapter import (_AdapterManager, _AdapterMeta, _DefaultFormat)

log = logging.getLogger(__name__)

AdapterOptionKeyConversion = 'conversion'
AdapterOptionKeyRecurseIf = 'recurse if'
AdapterOptionKeyClass = 'adapt to class'


def AdaptToClass(obj, dst_class, format=_DefaultFormat):
    adapter = _AdapterManager().lookup_adapter(type(obj), dst_class, format)()
    return adapter.adapt(obj)


def ListConverter(dst_class, format=_DefaultFormat):

    def adapt_list(lst):
        log.debug('Adapt list to %r', dst_class.__name__)
        return [AdaptToClass(_x, dst_class, format=format) for _x in lst]

    return adapt_list


class AdapterProperty(object):

    def __init__(self, to_class, format=_DefaultFormat):
        if not isinstance(to_class, type):
            raise TypeError(
                'to_class must be a type (i.e. class), was %r' % to_class)

        self.__to_class = to_class
        self.__format = format

    def __get__(self, obj, owner):
        if obj is None:
            return self

        try:
            adapter = _AdapterManager().lookup_adapter(
                owner, self.__to_class, self.__format)()
        except AttributeError as exc:
            log.debug(
                'AttributeError looking up / creating adapter from %r to %r',
                owner.__name__, self.__to_class.__name__, exc_info=True)
            raise
        except Exception as exc:
            log.debug(
                'Exception looking up / creating adapter from %r to %r: '
                '\'%s\'', owner.__name__, self.__to_class.__name__, exc)
            raise

        log.debug('Adapt using %r adapter.', type(adapter).__name__)
        try:
            adapted = adapter.adapt(obj)
        except Exception as exc:
            log.exception('Exception using %r adapter', type(adapter).__name__)
            raise

        log.debug('Adapt using %r adapter - COMPLETE', type(adapter).__name__)
        return adapted


@add_metaclass(_AdapterMeta)
class BaseAdapter(Singleton):

    # Tell singleton we want it to remember our references.
    UseStrongReferences = True

    @abstractproperty
    def from_class(self):
        raise AttributeError(
            'BaseAdapter does not implement the from_class property.')

    @abstractproperty
    def to_class(self):
        raise AttributeError(
            'BaseAdapter does not implement the to_class property.')

    @abstractproperty
    def adaptations(self):
        raise AttributeError(
            'BaseAdapter does not implement the to_class property.')

    @abstractmethod
    def adapt(self, from_obj):
        raise AttributeError(
            'BaseAdapter does not implement the adapt method.')


class SelfRegisteringAdapter(BaseAdapter):
    pass


class ProxyAdapter(SelfRegisteringAdapter):
    """This is an adapter that maintains a proxy object for the adapted object,
    which dynamically adapts the interface, rather than providing a snapshot
    object at each call to adapt.
    """

    def __init__(self):
        super(ProxyAdapter, self).__init__()
        self.__proxy_type = type(
            '_ProxyFor' + self.to_class.__name__,
            (self._new_proxy_class(), self.to_class), {})

    def adapt(self, from_obj):
        proxy = getattr(from_obj, self._proxy_attribute_name, None)
        if proxy is not None:
            log.debug('Use existing proxy adapter')
            return proxy

        log.debug(
            'Create new proxy adapter type is %r', self.__proxy_type.__name__)
        log.detail('Proxy type mro is %r', self.__proxy_type.__mro__)
        new_proxy = self.__proxy_type(from_obj)

        log.debug('Set new proxy')
        setattr(from_obj, self._proxy_attribute_name, new_proxy)
        return new_proxy

    #
    # =================== INTERNAL INTERFACE ==================================
    #
    @property
    def _proxy_attribute_name(self):
        return '_%s_adapter_proxy' % self.to_class.__name__

    def _new_proxy_class(self):

        class_dict = {}
        for adaptation in self.adaptations:

            exposed_attr = adaptation[0]
            if not isinstance(exposed_attr, str):
                raise TypeError(
                    'Bad type for an attribute declared for adapter adapting '
                    '%s to %s: %r' % (
                        self.from_class.__name__, self.to_class.__name__,
                        exposed_attr))

            underlying_attr_or_options = adaptation[1]
            if isinstance(underlying_attr_or_options, str):
                underlying_attr = underlying_attr_or_options
                if len(adaptation) > 2:
                    options = adaptation[2]
                else:
                    options = {}
            else:
                underlying_attr = None
                options = underlying_attr_or_options

            class_dict[exposed_attr] = ProxyProperty(
                exposed_attr, underlying_attr, options)

        return type('_Proxy', (Proxy,), class_dict)


class ProxyProperty(object):

    _underlying_object_attrname = '_adapted_object'

    def __init__(self, attr_to_expose, attr_to_adapt, options=None):

        self.__attr_to_expose = attr_to_expose
        self.__attr_to_adapt = attr_to_adapt

        if options is None:
            options = {}
        elif not isinstance(options, Mapping):
            raise TypeError(
                'Bad type %r for options of %r attribute (must be a '
                'Mapping)' % (options.__class__, attr_to_adapt))

        self.__adapt_to_class = options.get(AdapterOptionKeyClass, None)
        if (self.__adapt_to_class is not None and
                not isinstance(self.__adapt_to_class, type)):
            raise TypeError(
                'AdapterOptionKeyClass value must be a or None, is: %r' % (
                    self.__adapt_to_class))

        self.__converter = options.get(AdapterOptionKeyConversion, None)
        self.__recurse_condition = options.get(AdapterOptionKeyRecurseIf, None)

    def __get__(self, obj, owner):
        if obj is None:
            return self

        log.debug(
            'Get proxied object for its %r attribute', self.__attr_to_adapt)
        wr = getattr(obj, self._underlying_object_attrname)
        adapted_object = wr()
        if adapted_object is None:
            log.debug(
                'No underlying object for %r instance', obj.__class__.__name__)
            raise AttributeError(
                'The adapted object has been freed so the %r instance cannot '
                'generate its attributes.' % (obj.__class__.__name__)
            )

        log.debug('Get attribute %r of proxied object', self.__attr_to_adapt)
        if self.__attr_to_adapt is None:
            # If we weren't specified an attribute to adapt, we should just
            # pass the whole underlying object.
            val = adapted_object
        else:
            val = getattr(adapted_object, self.__attr_to_adapt)

        log.debug('Got raw value %r', val)

        if self.__adapt_to_class is not None:
            val = AdaptToClass(val, self.__adapt_to_class)

        if self.__converter is not None:
            val = self.__converter(val)

        if self.__recurse_condition is not None:
            if self.__recurse_condition(val):

                # So the MRO looks like ('_ProxyFor<Class>', '_Proxy'
                # (specialization of ...), 'Proxy', '<Class>', ...) so we need
                # to  get the super of the 2nd item in the MRO to recurse to
                # get the value from the original class, as requested.
                sp = super(owner.__mro__[2], obj)
                val = getattr(sp, self.__attr_to_expose)

        return val

    def __set__(self, obj, value):

        # We ignore the set. This is because there may be some default
        # initialization by the class that we don't want to break, but don't
        # actually want to do anything with.
        if log.getEffectiveLevel() >= logging.DEBUG:
            wr = getattr(obj, self._underlying_object_attrname)

            adapted_object = wr()
            log.debug(
                'Attempt to set proxy property (proxied %r instance '
                'attribute %r) to %r instance has been ignored.',
                type(adapted_object).__name__, self.__attr_to_adapt,
                type(value).__name__)


class Proxy(object):

    def __init__(self, adapted_object):
        self.__dict__[ProxyProperty._underlying_object_attrname] = ref(
            adapted_object)
        super(Proxy, self).__init__()
