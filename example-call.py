# import sip
import sys
import pdb


class Meta1(type):

    def __new__(cls, name, bases, dict):

        dict["meta1attr"] = 3
        dict["meta2attr"] = 3
        return super(Meta1, cls).__new__(cls, name, bases, dict)


class Meta2(type):

    def __new__(cls, name, bases, dict):

        dict["meta2attr"] = 5
        dict["meta1attr"] = 5
        return super(Meta2, cls).__new__(cls, name, bases, dict)


class A(object):

    class _AMC(Meta2, Meta1):
        pass
    __metaclass__ = _AMC

print(A.meta1attr)
print(A.meta2attr)
