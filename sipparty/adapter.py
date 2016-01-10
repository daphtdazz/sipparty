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
from abc import (ABCMeta, abstractmethod, abstractproperty)
import logging
from six import add_metaclass
from weakref import ref
from ._adapter import (
    AdapterError, AdapterAlreadyExistsError, NoSuchAdapterError,
    _AdapterManager, _AdapterMeta, _DefaultFormat)

log = logging.getLogger(__name__)

AdapterOptionKeyConversion = 'conversion'


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

        adapter = _AdapterManager().lookup_adapter(
            owner, self.__to_class, self.__format)()

        return adapter.adapt(obj)


class BaseAdapter(object):

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


@add_metaclass(_AdapterMeta)
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
            (NewProxyWithAdaptations(self.adaptations), self.to_class), {})

    def adapt(self, from_obj):
        log.debug(
            'Adapt %r instance to %r', from_obj.__class__.__name__,
            self.to_class.__name__)
        proxy = getattr(from_obj, self._proxy_attribute_name, None)
        if proxy is not None:
            return proxy

        log.debug('Proxy type is %r', self.__proxy_type.__name__)
        log.detail('Proxy type mro is %r', self.__proxy_type.__mro__)
        new_proxy = self.__proxy_type(from_obj)
        setattr(from_obj, self._proxy_attribute_name, new_proxy)
        return new_proxy

    #
    # =================== INTERNAL INTERFACE ==================================
    #
    @property
    def _proxy_attribute_name(self):
        return '_%s_adapter_proxy' % self.to_class.__name__


class ProxyProperty(object):

    def __init__(self, attr_to_adapt, options=None):

        self.__attr_to_adapt = attr_to_adapt

        if options is None:
            options = {}

        self.__converter = options.get(AdapterOptionKeyConversion, None)

    def __get__(self, obj, owner):
        if obj is None:
            return self

        wr = obj._adapted_object
        adapted_object = wr()
        if adapted_object is None:
            raise AttributeError(
                'The adapted object has been freed so the %r instance cannot '
                'generate its attributes.' % (obj.__class__.__name__)
            )
        val = getattr(adapted_object, self.__attr_to_adapt)
        if self.__converter is not None:
            val = self.__converter(val)
        return val


class Proxy(object):

    def __init__(self, adapted_object):
        super(Proxy, self).__init__()
        self._adapted_object = ref(adapted_object)


def NewProxyWithAdaptations(adaptations):

    class_dict = {
        adaptation[0]: ProxyProperty(*adaptation[1:])
        for adaptation in adaptations
    }
    return type('_Proxy', (Proxy,), class_dict)

