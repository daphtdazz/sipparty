import six
import sys
import threading
import sip._util
import logging

log = logging.getLogger()
log.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)


class TDesc(object):
    def __get__(self, obj, typ=None):
        if obj is not None:
            if hasattr(obj, "_val"):
                return getattr(obj, "_val")
            return 14

        return 13

    def __set__(self, obj, val):
        setattr(obj, "_val", val)


class PTest(object):

    dp = sip._util.DerivedProperty("_pt_dp")

    desc = TDesc()

    def __init__(self):
        self.__dict__['_pt_dp'] = 1
        self.__dict__['desc'] = 15
        self.__dict__['prop'] = 15

    @classmethod
    def tClassM(cls):
        log.info("PTest tClassM")


class QTest(PTest):

    dp = sip._util.DerivedProperty("_pt_dp", get="get_dp", set="set_dp")

    def get_dp(self):
        if '_new_pt_dp' in self.__dict__:
            return self.__dict__['_new_pt_dp']
        return 2

    def set_dp(self, val):
        self.__dict__['_new_pt_dp'] = val

    desc = TDesc()

    @property
    def prop(self):
        return 14

    @classmethod
    def tClassM(cls):
        log.info("Before PTest tClassM")
        super(QTest, cls).tClassM()
        log.info("After PTest tClassM")

    def __getattr__(self, attr):
        log.info("Get attr %r.", attr)

PTest.dp = 2
log.info("%r", PTest.dp)
