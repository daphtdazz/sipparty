# import sip
import sys
import pdb


class A(object):

    def __init__(self):
        self.a = None


class B(object):
    pass

import datetime


def ts():
    now = datetime.datetime.now()

    return "%02d:%02d.%06d" % (now.minute, now.second, now.microsecond)

print "test attr is None"
print ts()

a = A()
z = 0
repeats = 1000000
for ii in range(repeats):

    if a.a is None:
        z += 1


print ts()

b = B()
zz = 0
for ii in range(repeats):

    if not hasattr(b, "b"):
        zz += 1

print ts()
assert z == zz

print "test getattr hasattr when no attr"
print ts()
z = 0
for ii in range(repeats):

    try:
        getattr(b, "d")
    except AttributeError:
        z += 1

print ts()
zz = 0
for ii in range(repeats):
    if not hasattr(b, "d"):
        zz += 1

print ts()
assert z == zz

print "test getattr hasattr when attr"
print ts()
z = 0
for ii in range(repeats):

    val = getattr(a, "a")
    z += 1

print ts()
zz = 0
for ii in range(repeats):
    if hasattr(a, "a"):
        val = getattr(a, "a")
        zz += 1

print ts()
assert z == zz

quit()


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
