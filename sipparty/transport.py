"""transport.py

Implements a transport layer.

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
import socket
import threading
import time
import collections
import logging
import select
from socket import (SOCK_STREAM, SOCK_DGRAM, AF_INET, AF_INET6)
from numbers import Integral
import re
from sipparty import (fsm, FSM, RetryThread)
from sipparty.util import (
    DerivedProperty, WeakMethod, Singleton, TwoCompatibleThree, Enum)

SOCK_TYPES = Enum((SOCK_STREAM, SOCK_DGRAM))
SOCK_TYPES_NAMES = Enum(("SOCK_STREAM", "SOCK_DGRAM"))
SOCK_TYPE_IP_NAMES = Enum(("TCP", "UDP"))
SOCK_FAMILIES = Enum((AF_INET, AF_INET6))
SOCK_FAMILY_NAMES = Enum(("IPv4", "IPv6"))
log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")
bytes = six.binary_type
itervalues = six.itervalues
IPv4RE = re.compile("([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})")
IPv6RE = re.compile("")

# RFC 2373 IPv6 address format definitions.
digitrange = b"0-9"
DIGIT = b"[{digitrange}]".format(**locals())
hexrange = b"{digitrange}a-fA-F".format(**locals())
HEXDIG = b"[{hexrange}]".format(**locals())
hex4 = b"{HEXDIG}{{1,4}}".format(**locals())
# Surely IPv6 address length is limited?
hexseq = b"{hex4}(?::{hex4})*".format(**locals())
hexpart = b"(?:{hexseq}|{hexseq}::(?:{hexseq})?|::(?:{hexseq})?)".format(
    **locals())
IPv4address = b"{DIGIT}{{1,3}}(?:[.]{DIGIT}{{1,3}}){{3}}".format(**locals())
IPv6address = b"{hexpart}(?::{IPv4address})?".format(**locals())
port = b"{DIGIT}+".format(**locals())


class TransportException(Exception):
    pass


@TwoCompatibleThree
class UnresolvableAddress(TransportException):

    def __init__(self, address, port):
        super(UnresolvableAddress, self).__init__()
        self.address = address
        self.port = port

    def __bytes__(self):
        return "The address:port %r:%r was not resolvable." % (
            self.address, self.port)


@TwoCompatibleThree
class BadNetwork(TransportException):

    def __init__(self, msg, socketError):
        super(BadNetwork, self).__init__(msg)
        self.socketError = socketError

    def __bytes__(self):
        sp = super(BadNetwork, self)
        sms = sp.__bytes__() if hasattr(sp, "__bytes__") else sp.__str__()
        return "%s. Socket error: %s" % (sms, self.socketError)


def SockFamilyName(family):
    return SOCK_FAMILY_NAMES[SOCK_FAMILIES.index(family)]


def SockTypeName(socktype):
    if socktype == socket.SOCK_STREAM:
        return "TCP"
    if socktype == socket.SOCK_DGRAM:
        return "UDP"
    assert socktype in (socket.SOCK_STREAM, socket.SOCK_DGRAM)


def GetBoundSocket(family, socktype, address):

    if family is None:
        family = 0
    if socktype is None:
        socktype = 0
    assert family in (0, socket.AF_INET, socket.AF_INET6)
    assert socktype in (0, socket.SOCK_STREAM, socket.SOCK_DGRAM)

    address = list(address)
    if address[0] is None:
        address[0] = socket.gethostname()

    # family e.g. AF_INET / AF_INET6
    # socktype e.g. SOCK_STREAM
    # Just grab the first addr info if we haven't
    log.debug("GetBoundSocket addr:%r port:%r family:%r socktype:%r...",
              address[0], address[1], family, SockTypeName(socktype))

    addrinfos = socket.getaddrinfo(address[0], address[1], family, socktype)
    log.debug("Got addresses.")
    log.detail("  %r", addrinfos)

    if len(addrinfos) == 0:
        raise BadNetwork("Could not find an address to bind to %r." % address)

    _family, _socktype, _proto, _canonname, address = addrinfos[0]

    ssocket = socket.socket(_family, socktype)

    def port_generator():
        if address[1] != 0:
            # The port was specified.
            yield address[1]
            return

        # Guess a port from the unregistered range.
        for ii in range(49152, 0x10000):
            yield ii

    socketError = None
    for port in port_generator():
        try:
            # TODO: catch specific errors (e.g. address in use) to bail
            # immediately rather than inefficiently try all ports.
            ssocket.bind(address)
            break
        except socket.error as socketError:
            pass
        except socket.gaierror as socketError:
            break

    if socketError is not None:
        raise BadNetwork(
            "Couldn't bind to address {address}".format(
                **locals()),
            socketError)

    log.debug("Socket bound to %r type %r", ssocket.getsockname(), _family)
    return ssocket


class Transport(Singleton):
    """Manages connection state and transport so You don't have to."""
    #
    # =================== CLASS INTERFACE =====================================
    #
    DefaultTransportType = SOCK_DGRAM
    DefaultPort = 0
    DefaultFamily = AF_INET

    @classmethod
    def FormatBytesForLogging(cls, mbytes):
        return "\\n\n".join(
            [repr(bs)[1:-1] for bs in mbytes.split("\n")]).rstrip("\n")

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    byteConsumer = DerivedProperty("_tp_byteConsumer")

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

    def resolveHost(self, host, port=None, family=None):
        """Resolve a host.
        :param bytes host: A host in `bytes` form that we want to resolve.
        May be a domain name or an IP address.
        :param integer,None port: A port we want to connect to on the host.
        """
        if port is None:
            port = self.DefaultPort
        if not isinstance(port, Integral) or 0 > port > 0xffff:
            raise ValueError("Invalid port: %r", port)
        if family not in (None, AF_INET, AF_INET6):
            raise ValueError("Invalid socket family %r" % family)

        try:
            ais = socket.getaddrinfo(host, port)
            log.debug(
                "Options for address %r:%r family %r are %r.", host, port,
                family, ais)
            for ai in ais:
                if family is not None and ai[0] != family:
                    continue
                return ai[4]
        except socket.gaierror as exc:
            pass

        raise(UnresolvableAddress(address=host, port=port))

    def sendMessage(self, msg, toAddr, sockType=None):
        sockType = self.fixSockType(sockType)
        if sockType == SOCK_DGRAM:
            return self.sendDgramMessage(msg, toAddr)

        return self.sendStreamMessage(msg, toAddr)

    def sendDgramMessage(self, msg, toAddr):
        mbytes = bytes(msg)
        log.debug("Send to %r", toAddr)

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
            sname = sck.getsockname()
            try:
                if len(toAddr) != len(sname):
                    log.debug("Different socket family type skipped.")
                    continue
                sck.sendto(mbytes, toAddr)
                prot_log.info(
                    "Sent %r -> %r\n>>>>>\n%s\n>>>>>", sname,
                    toAddr, self.FormatBytesForLogging(mbytes))
                return
            except socket.error as exc:
                log.debug(
                    "Could not sendto %r from %r: %s", toAddr,
                    sname, exc)
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
                " received %r -> %r\n<<<<<\n%s\n<<<<<", rAddr, lAddr,
                self.FormatBytesForLogging(data))
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
        if not isinstance(data_consumed, Integral):
            raise ValueError(
                "byteConsumer returned %r: must return an integer." % (
                    data_consumed,))
        return data_consumed