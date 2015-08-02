"""siptransport.py

Specializes the transport layer for SIP.

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import six
import logging
import socket
from socket import (SOCK_STREAM, SOCK_DGRAM, AF_INET, AF_INET6)
SOCK_TYPES = (SOCK_STREAM, SOCK_DGRAM)
SOCK_TYPES_NAMES = ("SOCK_STREAM", "SOCK_DGRAM")
SOCK_FAMILIES = (AF_INET, AF_INET6)

from sipparty.util import WeakMethod
from sipparty import RetryThread, util
import transport
from transport import (GetBoundSocket,)
#import prot
#import message
#import collections

log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")
prot_log.setLevel(logging.INFO)
bytes = six.binary_type
itervalues = six.itervalues


if False:
    class DGramCachedSocket(object):

        def __init__(self):
            super(DGramCachedSocket, self).__init__()
            self._dcs_sck = sck
            self._dcs_toAddresses = []

        def addToAddress(self, toAddr):
            self._dcs_toAddresses.append(toAddr)

        def toAddresses(self):
            for toAddr in self._dcs_toAddresses:
                yield toAddr

        def sockname(self):
            return self._dcs_sck.sockname()


class Transport(object):
    """Manages connection state and transport so You don't have to."""
    #
    # =================== CLASS INTERFACE =====================================
    #
    DefaultTransportType = SOCK_DGRAM

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    byteConsumer = util.DerivedProperty("_tp_byteConsumer")
    def __init__(self):
        super(Transport, self).__init__()
        self._tp_byteConsumer = None
        self._tp_retryThread = RetryThread()
        self._tp_retryThread.start()

        # Keyed by (lAddr, rAddr) independent of type.
        self._tp_connBuffers = {}
        # Keyed by local address tuple.
        self._tp_dGramSockets = {}
        # Keyed by toAddr, which is some hashable, so might be a proper tuple
        # address or it might just be a hostname.

        for fam in SOCK_FAMILIES:
            self.addDgramSocket(socket.socket(fam, SOCK_DGRAM))

    def addToHandler(self, uri, handler):
        # TODO: rename this to addNewDialog handler, and split out SIP specific
        # parts from transport parts.

        hdlrs = self._sptr_toHandlers
        if handler in hdlrs:
            raise KeyError(
                "To handler already registered for URI %r" % bytes(uri))

        hdlrs[handler] = uri

    def removeToHandler(self, uri):

        hdlrs = self._sptr_toHandlers
        if handler not in hdlrs:
            raise KeyError(
                "To handler not registered for URI %r" % bytes(uri))

        del hdlrs[handler]

    def sendMessage(self, msg, toAddr, sockType=None):
        sockType = self.fixSockType(sockType)
        if sockType == SOCK_DGRAM:
            return self.sendDgramMessage(msg, toAddr)

        return self.sendStreamMessage(msg, toAddr)

    def sendDgramMessage(self, msg, toAddr):
        mbytes = bytes(msg)

        if False:
            # First see if there's a cached socket we can use. If not, try the
            # existing sockets in turn. Else create a new one by connecting,
            # learning, and listening.
            dgcscks = self._sptr_dGramCachedToSocks
            log.debug("Cached sockets: %r", dgcscks)

            if toAddr in dgcscks:
                cachedSock = dgcscks[toAddr]
                try:
                    return self.sendDgramToCachedSock(cachedSock)
                except socket.error as exc:
                    log.warning(
                        "Existing socket to %r from %r had error: %s", toAddr,
                        cachedSock.sockname(), exc)
                    self.uncacheDgramSock(cachedSock)

        # No cached socket, try existing sockets in turn.
        for sck in itervalues(self._tp_dGramSockets):
            try:
                sck.sendto(mbytes, toAddr)
                prot_log.info(
                    "Sent %r -> %r\n>>>>>\n%s\n>>>>>", sck.getsockname(),
                    toAddr, mbytes)
                return
            except socket.error as exc:
                log.debug(
                    "Could not sendto %r with family %d", toAddr, sck.family)
        else:
            raise exc

    def addDgramSocket(self, sck):
        self._tp_dGramSockets[sck.getsockname()] = sck

    def listen(self, sockType=None, lHostName=None, port=None):
        sockType = self.fixSockType(sockType)
        if sockType not in SOCK_TYPES:
            raise ValueError(
                "Listen socket type must be one of %r" % (SOCK_TYPES_NAMES,))

        if sockType == SOCK_DGRAM:
            return self.listenDgram(lHostName, port)

        return self.listenStream(lHostName, port)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        log.debug("Deleting Transport")
        sp = super(Transport, self)
        if hasattr(sp, "__del__"):
            sp.__del__()

    #
    # =================== INTERNAL METHODS ====================================
    #
    def fixSockType(self, sockType):
        if sockType is None:
            sockType = self.DefaultTransportType
        return sockType

    def listenDgram(self, lAddrName, port):
        sock = GetBoundSocket(None, SOCK_DGRAM, (lAddrName, port))
        rt = self._tp_retryThread
        rt.addInputFD(sock, WeakMethod(self, "dgramDataAvailable"))
        self.addDgramSocket(sock)
        return sock.getsockname()

    def dgramDataAvailable(self, sck):
        data, address = sck.recvfrom(4096)
        self.receivedData(sck.getsockname(), address, data)

    def receivedData(self, lAddr, rAddr, data):
        if len(data) > 0:
            prot_log.info(
                " received %r -> %r\n<<<<<\n%s\n<<<<<", rAddr, lAddr, data)
        connkey = (lAddr, rAddr)
        bufs = self._tp_connBuffers
        if connkey not in bufs:
            buf = bytearray()
            bufs[connkey] = buf
        else:
            buf = bufs[connkey]

        buf.extend(data)

        while len(buf) > 0:
            len_used = self.processReceivedData(buf)
            if len_used == 0:
                log.debug("Consumer stopped consuming")
                break
            log.debug("Consumer consumed another %d bytes", len_used)
            del buf[:len_used]

    def processReceivedData(self, data):

        bc = self.byteConsumer
        if bc is None:
            log.debug("No consumer; dumping data: %r.", data)
            return len(data)

        data_consumed = bc(bytes(data))


class SIPTransport(Transport):
    """SIP specific subclass of Transport."""
    #
    # =================== INSTANCE INTERFACE ==================================
    #
    def __init__(self):
        super(SIPTransport, self).__init__()
        self._sptr_toHandlers = {}

    def addToHandler(self, uri, handler):
        # TODO: rename this to addNewDialog handler, and split out SIP specific
        # parts from transport parts.

        hdlrs = self._sptr_toHandlers
        if handler in hdlrs:
            raise KeyError(
                "To handler already registered for URI %r" % bytes(uri))

        hdlrs[handler] = uri

    def removeToHandler(self, uri):

        hdlrs = self._sptr_toHandlers
        if handler not in hdlrs:
            raise KeyError(
                "To handler not registered for URI %r" % bytes(uri))

        del hdlrs[handler]

    def sendMessage(self, msg, toAddr, sockType=None):
        super(SIPTransport, self).sendMessage(
            bytes(msg), toAddr, sockType=sockType)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        log.debug("Deleting SIPTransport")
        sp = super(SIPTransport, self)
        if hasattr(sp, "__del__"):
            sp.__del__()

    #
    # =================== INTERNAL METHODS ====================================
    #
