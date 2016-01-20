"""_adapter.py

Internal classes and modules for the adapter implementation.

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
from abc import (ABCMeta, abstractproperty)
import logging
from .util import (Singleton, SingletonType)

log = logging.getLogger(__name__)


class AdapterError(Exception):

    def __init__(self, src_class, dst_class, format):
        msg = 'Source class: %s, destination class: %s, format: %r' % (
            src_class.__name__, dst_class.__name__, format)

        super(AdapterError, self).__init__(msg)


class AdapterAlreadyExistsError(AdapterError):
    pass


class NoSuchAdapterError(AdapterError):
    pass


_DefaultFormat = ''


class _AdapterMeta(ABCMeta, SingletonType):

    def __new__(cls, *args, **kwargs):

        new_adapter = super(_AdapterMeta, cls).__new__(cls, *args, **kwargs)

        from_class = new_adapter.from_class
        to_class = new_adapter.to_class
        format = getattr(new_adapter, 'adapter_format', _DefaultFormat)
        if all([not isinstance(_obj, abstractproperty)
                for _obj in (from_class, to_class)]):
            _AdapterManager().register(
                new_adapter, from_class, to_class, format)

        return new_adapter


class _AdapterManager(Singleton):
    """

    NB: not yet threadsafe (register at least is not).
    """

    # Override shared instances to make sure they stick around (not weak
    # instances).
    _St_SharedInstances = {}

    def __init__(self, *args, **kwargs):

        log.debug('Initial init of _AdapterManager singleton')
        super(_AdapterManager, self).__init__(*args, **kwargs)

        # Full layout might be something like:
        # {
        #   Class1: {
        #       Class2: {
        #           'format1': Class1ToClass2Format1Adapter
        #       }
        #   }
        # }
        self.__adapters = {}

    def register(self, adapter, src_class, dst_class, format=_DefaultFormat):
        log.debug(
            'Register %r adapter from %r to %r format %r', adapter.__name__,
            src_class.__name__, dst_class.__name__, format
        )
        dst_class_dict = self.__adapters.get(src_class, {})
        self.__adapters[src_class] = dst_class_dict

        format_dict = dst_class_dict.get(dst_class, {})
        dst_class_dict[dst_class] = format_dict

        format_entry = format_dict.get(format, None)

        if format_entry is not None:
            raise AdapterAlreadyExistsError(src_class, dst_class, format)

        format_dict[format] = adapter

        log.detail('adapter dictionary now %r', self.__adapters)

    def lookup_adapter(self, src_class, dst_class, format=_DefaultFormat):
        log.debug(
            'Lookup adapter for conversion from %r to %r format %r',
            src_class.__name__, dst_class.__name__, format
        )
        log.detail('  Adapters dictionary: %r', self.__adapters)
        for cls in (src_class,) + src_class.__mro__:
            dst_class_dict = self.__adapters.get(cls, None)
            if dst_class_dict is None:
                continue

            format_dict = dst_class_dict.get(dst_class, None)
            if format_dict is None:
                continue

            format_entry = format_dict.get(format, None)
            if format_entry is None:
                continue

            break
        else:
            raise NoSuchAdapterError(src_class, dst_class, format)

        return format_entry

    def unregister(self, src_class, dst_class, format=_DefaultFormat):
        dst_class_dict = self.__adapters.get(src_class, None)
        if dst_class_dict is None:
            raise NoSuchAdapterError(src_class, dst_class, format)

        format_dict = dst_class_dict.get(dst_class, None)
        if format_dict is None:
            raise NoSuchAdapterError(src_class, dst_class, format)

        format_entry = format_dict.get(format, None)
        if format_entry is None:
            raise NoSuchAdapterError(src_class, dst_class, format)

        del format_dict[format]
