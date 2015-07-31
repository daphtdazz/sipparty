import six
import sys
import threading
import time
import logging
import socket

lsck1 = socket.socket(type=socket.SOCK_DGRAM)
lsck2 = socket.socket(type=socket.SOCK_DGRAM)
asck2 = socket.socket(type=socket.SOCK_DGRAM)

sock1 = 5062
sock2 = 5063
sock3 = 5064

lsck1.bind(("127.0.0.1", sock1))

lsck2.connect(("127.0.0.1", sock1))

lsck2.send("hello")

print("lsck2 name: %r" % (lsck2.getsockname(),))

sname = lsck2.getsockname()
lsck2.shutdown(socket.SHUT_WR)
lsck2.close()
asck2.bind(sname)

data, addr = lsck1.recvfrom(4096)

print("%r from %r" % (data, addr))
