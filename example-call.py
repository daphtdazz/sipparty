import six
import sys
import threading
import time
import sip._util
import logging

log = logging.getLogger()
log1 = logging.getLogger("a")

logging.basicConfig()

log.warning("Warning from root")
log.info("Warning from root")
log.debug("Hello from root")
log1.debug("Hello from a")
