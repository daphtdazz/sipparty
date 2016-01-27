from __future__ import print_function
from cProfile import run
from sipparty.vb import ValueBinder


def notamethod(self):
    self.__notanattr = 5


class PerfTestClass(object):

    def __init__(self):
        self.somevar = 3
        self.__private_var = 5

    mymethod = notamethod


class PerfTestSubClass(object):
    pass

PerfTestClass.__name__ = 'renamed'

ptc = PerfTestClass()
ptc.mymethod()

invs = []
run('for ii in range(10): invs.append(Message.invite())', sort='cumtime')
print('%r' % ValueBinder.set_attr_calls)
print('%r' % ValueBinder.init_calls)
