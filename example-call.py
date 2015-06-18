import six
import sys
import threading
import time
import logging


class X(object):

    def __getattr__(self, attr):

        if attr == "a":
            return 1

        raise AttributeError("X has not attribute %r" % attr)

print X.__getattr__(X(), "a")
