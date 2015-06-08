import six
import sys
import threading
import time
import sip._util
import logging


def gen2():
    yield "c"
    yield "d"


def gen():
    yield "a"
    yield "b"
    for ln in gen2():
        yield ln

print(",".join(gen()))
