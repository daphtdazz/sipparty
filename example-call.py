import six
import sys
import threading
import time
import sip._util
import logging

log = logging.getLogger()
log.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)


def method():
    log.info("method")

thr = threading.Thread(target=method)
thr.start()

time.sleep(1)
