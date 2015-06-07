import six
import sys
import threading
import time
import sip._util
import logging


def gen():
    yield "a"
    yield "b"

print(",".join(gen()))
