import six
import sys
import threading
import time
import logging


class X(object):

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, val):
        self._state = val

X.state = 2

x = X()

x.state = 3
print x._state
