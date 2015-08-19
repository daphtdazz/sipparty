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


class MySubClass(MyClass):
    @property
    def prop(self):
        return True

mc = MyClass()
ms = MySubClass()
print mc.prop
print ms.prop
