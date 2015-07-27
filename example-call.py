import six
import sys
import threading
import time
import logging
import socket

lsck1 = socket.socket(type=socket.SOCK_DGRAM)
asck2 = socket.socket(type=socket.SOCK_DGRAM)

lsck1.bind(("127.0.0.1", 5060))

asck2.connect(("127.0.0.1", 5060))

asck2.send("hello lsck1")

data, asck2_address = lsck1.recvfrom(1)

print("%s from %r" % (data, asck2_address))

asck1 = lsck1
asck1.connect(asck2_address)

lsck1 = socket.socket(type=socket.SOCK_DGRAM)
lsck1.bind(("127.0.0.1", 5060))


