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

    attr1 = 2
    attr2 = 3
    del attr1

print MyClass.attr2
print MyClass.attr1
