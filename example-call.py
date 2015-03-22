# import sip
import sys
import pdb
import logging

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)


class A(object):

    def dec(method):
        log.debug("decorating")

        def call_meth(self):
            log.debug("Call wrapped method")
            return method(self)

        return call_meth

    @dec
    def wrapped(self):
        log.debug("wrapped")

a = A()
a.wrapped()
a.dec()
