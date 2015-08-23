import six
import sys
import threading
import time
import logging
import socket
import weakref

logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.DEBUG)


class MyClass(object):

    @property
    def prop(self):
        return False

    def __getattr__(self, attr):
        print("super getattr")
        if attr == "superAttr":
            return 1234
        raise AttributeError()


class MySubClass(MyClass):
    @property
    def prop(self):
        return True

    def __getattr__(self, attr):
        print("sub getattr")
        if attr == "superAttr":
            sp = super(MySubClass, self)
            if hasattr(sp, "__getattr__"):
                return sp.__getattr__(attr)

        raise AttributeError("%r instance has no attr %r." % (
            self.__class__.__name__, attr))

ms = MySubClass()
print(ms.superAttr)
