import six
import sys
import threading
import time
import logging
import socket
import weakref

logging.basicConfig()
rlog = logging.getLogger()
rlog.setLevel(logging.WARNING)
rlog.debug("Nothing...")
rlog.warning("Warning")
alog = logging.getLogger("a")
alog.setLevel(logging.DEBUG)
alog.debug("debug me")
