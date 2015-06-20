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

from sipparty import (util, fsm)

log = logging.getLogger(__name__)
bytes = six.binary_type


class BadNetwork(Exception):
    pass


def SockFamilyName(family):
    if family == socket.AF_INET:
        return "IPv4"
    if family == socket.AF_INET6:
        return "IPv6"
    assert family in (socket.AF_INET, socket.AF_INET6)


def SockTypeName(socktype):
    if socktype == socket.SOCK_STREAM:
        return "TCP"
    if socktype == socket.SOCK_DGRAM:
        return "UDP"
    assert socktype in (socket.SOCK_STREAM, socket.SOCK_DGRAM)


def GetBoundSocket(family, socktype, address):

    assert family in (0, socket.AF_INET, socket.AF_INET6)
    assert socktype in (0, socket.SOCK_STREAM, socket.SOCK_DGRAM)

    address = list(address)
    if address[0] is None:
        address[0] = socket.gethostname()

    # family e.g. AF_INET / AF_INET6
    # socktype e.g. SOCK_STREAM
    # Just grab the first addr info if we haven't
    log.debug("getaddrinfo addr:%r port:%r family:%r socktype:%r",
              address[0], address[1], family, socktype)
    addrinfos = socket.getaddrinfo(address[0], address[1], family, socktype)

    if len(addrinfos) == 0:
        raise BadNetwork("Could not find an address to bind to %r." % address)

    _family, _socktype, _proto, _canonname, address = addrinfos[0]

    ssocket = socket.socket(family, socktype)

    def port_generator():
        if address[1] != 0:
            # The port was specified.
            yield address[1]
            return

        # Guess a port.
        yield 5060  # Always try 5060 first.
        for ii in range(15060, 0x10000):
            yield ii

    for port in port_generator():
        try:
            ssocket.bind(address)
            break
        except socket.error:
            pass
    else:
        raise BadNetwork(
            "Couldn't bind to address {address}.".format(
                **locals()))

    return ssocket


class TransportFSM(fsm.FSM):
    """Controls a socket connection
    """

    #
    # =================== CLASS INTERFACE ====================================
    #
    States = util.Enum(
        ("disconnected",
         "startListen",
         "listening",
         "connecting",
         "connected",
         "error"))
    Inputs = util.Enum(
        ("connect", "listen", "listenup", "connected",
         "send",
         "disconnect", "error",
         "reset"))
    Actions = util.Enum(
        ("createConnect", "attemptConnect",
         "createListen", "startListening", "becomesConnected",
         "connectedSend",
         "becomesDisconnected", "transportError"))

    @classmethod
    def AddClassTransitions(cls):

        S = cls.States
        I = cls.Inputs
        A = cls.Actions
        Add = cls.addTransition

        Add(S.disconnected, I.disconnect, S.disconnected)

        # Transitions when connecting out.
        Add(S.disconnected, I.connect, S.connecting,  # Start connecting.
            action=A.createConnect,
            start_threads=[A.attemptConnect])
        Add(S.connecting, I.error, S.error,
            action=A.transportError)
        Add(S.connecting, I.connected, S.connected,
            action=A.becomesConnected)

        # Transitions when listening.
        Add(S.disconnected, I.listen, S.startListen,
            action=A.createListen,
            start_threads=[A.startListening])
        Add(S.startListen, I.listenup, S.listening)
        Add(S.listening, I.error, S.error,
            action=A.transportError)
        Add(S.listening, I.connected, S.connected,
            action=A.becomesConnected)

        # Actions when in the connected state.
        Add(S.connected, I.send, S.connected,
            action=A.connectedSend)
        Add(S.connected, I.error, S.error,
            action=A.becomesDisconnected)
        Add(S.connected, I.disconnect, S.disconnected,
            action=A.becomesDisconnected)

        # Error in error and reset from an error.
        Add(S.error, I.reset, S.disconnected)

        # Start disconnected.
        cls.setState(S.disconnected)

    #
    # =================== INSTANCE INTERFACE =================================
    #
    family = util.DerivedProperty(
        "_tfsm_family", lambda val: val in (socket.AF_INET, socket.AF_INET6))
    socketType = util.DerivedProperty(
        "_tfsm_socketType",
        lambda val: val in (socket.SOCK_STREAM, socket.SOCK_DGRAM))

    localAddress = util.DerivedProperty("_tfsm_localAddress")
    localAddressPort = util.DerivedProperty(
        "_tfsm_localAddressPort",
        lambda val: 0 <= val <= 0xffff)
    localAddressHost = util.DerivedProperty("_tfsm_localAddressHost")
    byteConsumer = util.DerivedProperty(
        "_tfsm_byteConsumer",
        lambda val: isinstance(val, collections.Callable))
    remoteAddress = util.DerivedProperty("_tfsm_remoteAddressTuple")

    def __init__(self, socketType=socket.SOCK_STREAM, **kwargs):

        # The transport FSM is a root level independent FSM that schedules
        # its own work on a background thread, and to do this it uses the
        # asynchronous_timers feature of the FSM class.
        assert ("asynchronous_timers" not in kwargs or
                kwargs["asynchronous_timers"])
        kwargs["asynchronous_timers"] = True
        super(TransportFSM, self).__init__(**kwargs)

        self._tfsm_family = socket.AF_INET
        self.socketType = socketType

        la = self.__dict__["_tfsm_localAddress"] = [None, 0, 0, 0]
        self._tfsm_remoteAddressTuple = None

        self._tfsm_receiveSize = 4096
        self._tfsm_timeout = 2

        self._tfsm_listenSck = None
        self._tfsm_activeSck = None
        self._tfsm_buffer = bytearray()
        self._tfsm_byteConsumer = None

        # BSD (Mac OS X anyway) seems not to propagate an error to an accept
        # call on a socket if you close it from a different thread. So need
        # to use non-blocking sockets so that the accept loop can keep
        # checking whether the socket is still valid.
        #
        # This is also used for Datagram (UDP) sockets which use select to
        # wait for connections.
        self._tfsm_acceptSocketTimeout = 0.1

    # !!! These could be improved.
    @fsm.block_until_states((
        States.error, States.listening, States.connected))
    def listen(self, address=None, port=None):
        if address is not None:
            self.localAddress = address
        if port is not None:
            self.localAddressPort = port
        self.hit(self.Inputs.listen)

    @fsm.block_until_states((
        States.error, States.connecting, States.connected))
    def connect(self, *args, **kwargs):
        self.hit(self.Inputs.connect, *args, **kwargs)

    def send(self, data):
        self.hit(self.Inputs.send, data)

    @fsm.block_until_states((States.error, States.disconnected))
    def disconnect(self):
        self.hit(self.Inputs.disconnect)

    @fsm.block_until_states((States.disconnected))
    def reset(self):
        self.hit(self.Inputs.reset)

    #
    # =================== ACTIONS ============================================
    #
    # These actions are expected to be done synchronously on the main FSM
    # thread, therefore they should not block. Blocking function should be
    # done in the THREADS methods below.
    #
    # They should not be called directly; all interaction with the FSM should
    # be via one of the PUBLIC methods, and in particular the hit() method.
    #
    def createConnect(self, addr_tuple):

        log.info("Connect to %r.", addr_tuple)

        fam = self.family
        typ = self.socketType
        adr = self._tfsm_localAddress
        prt = self._tfsm_localAddressPort

        explen = 2 if fam == socket.AF_INET else 4

        if len(addr_tuple) != explen:
            self.hit(self.Inputs.error, "Bad address %r for %r socket." %
                     (addr_tuple, SockFamilyName(fam)))
            return

        try:
            self._tfsm_activeSck = GetBoundSocket(fam, typ, adr)
        # Need to add proper exception handling for socket errors here.
        except:
            log.error("Exception hit getting bound socket for connection.")
            self.hit(self.Inputs.error)
            raise

        self._tfsm_remoteAddressTuple = addr_tuple

    def createListen(self):
        try:
            self._tfsm_listenSck = GetBoundSocket(
                self.family, self.socketType, self._tfsm_localAddress)
        except Exception as exc:
            log.exception("Exception getting passive socket.")
            self.hit(self.Inputs.error,
                     "Exception getting passive socket: %r." % exc)
            return

        # Listen if it's a stream.
        if self._tfsm_listenSck.type == socket.SOCK_STREAM:
            log.debug("Listening for connections.")
            self._tfsm_listenSck.listen(0)

        self._tfsm_listenSck.settimeout(self._tfsm_acceptSocketTimeout)
        log.info(
            "Passive socket created on %r.",
            self._tfsm_listenSck.getsockname())

        log.debug("passive listen address: %r", self.localAddress)
        self.hit(self.Inputs.listenup)

    def becomesConnected(self):
        "Called when the transport becomes connected"
        self.addFDSource(self._tfsm_activeSck,
                         util.WeakMethod(self, "_tfsm_dataAvailable"))

    def becomesDisconnected(self):
        "Called when the transport goes down."
        self.rmFDSource(self._tfsm_activeSck)
        for sck in (self._tfsm_activeSck, self._tfsm_listenSck):
            if sck is not None:
                sck.close()
        self._tfsm_activeSck = None
        self._tfsm_listenSck = None

    def connectedSend(self, data):
        "Send some data."
        datalen = len(data)
        sck = self._tfsm_activeSck

        log.info("send\n>>>>>\n%s\n>>>>>", data)

        sent_bytes = sck.send(data)
        if sent_bytes != datalen:
            self.error("Failed to send %d bytes of data." %
                       (datalen - sent_bytes))

    def transportError(self, msg="unknown error"):
        "We've hit an error."
        self._tfsm_errormsg = msg
        if self._tfsm_listenSck is not None:
            log.debug("Error: close listen socket")
            self._tfsm_listenSck.close()
            self._tfsm_listenSck = None

        if self._tfsm_activeSck is not None:
            log.debug("Error: close active socket")
            self._tfsm_activeSck.close()
            self._tfsm_activeSck = None

        log.error(msg)

    #
    # =================== THREADS ============================================
    #
    def attemptConnect(self):
        "Attempt to connect out."
        log.debug("Attempt to connect to %r.", self._tfsm_remoteAddressTuple)
        sck = self._tfsm_activeSck
        if sck is None:
            log.debug("Create socket failed, so nothing to do.")
            return

        family = self.family
        sck_type = self.socketType
        address = self._tfsm_localAddress
        remote_address = self._tfsm_remoteAddressTuple

        try:
            self._tfsm_activeSck.connect(self._tfsm_remoteAddressTuple)
        except Exception as exc:
            self.hit(
                self.Inputs.error,
                "Exception connecting to %r: %r." %
                (self._tfsm_remoteAddressTuple, exc))
            return

        log.debug("Attempt connect done.")
        self.hit(self.Inputs.connected)

    def startListening(self):

        lsck = self._tfsm_listenSck

        if lsck is None:
            log.debug("Listen has been cancelled.")
            return

        # UDP socket.
        if lsck.type == socket.SOCK_DGRAM:
            log.debug("Datagram socket; wait for data on the socket.")

            fd = lsck.fileno()
            rsrcs, _, esrcs = select.select(
                [fd], [], [fd], self._tfsm_acceptSocketTimeout)
            if len(esrcs):
                self.hit(self.Inputs.error,
                         "Socket error on Datagram listen socket.")
                return

            if len(rsrcs) == 0:
                log.debug("No datagram yet, go around.")
                return 0

            log.debug("Data! We can get connected.")
            self._tfsm_activeSck = self._tfsm_listenSck
            self.hit(self.Inputs.connected)
            return

        # TCP socket.
        log.debug("Stream sockets: try and accept.")

        try:
            conn, addr = lsck.accept()
            self._tfsm_activeSck = conn
            self._tfsm_remoteAddressTuple = addr
            log.info("Connection accepted from %r.",
                     self._tfsm_remoteAddressTuple)
            self.hit(self.Inputs.connected)
            return
        except socket.timeout:
            # In this case we are going to try again straight away.
            log.debug("Socket timeout")
            return 0
        except Exception as exc:
            log.debug("Exception selecting listen socket", exc_info=True)
            self.hit(self.Inputs.error,
                     "Exception selecting listen socket %r." % exc)
            return

        log.debug("Start listening done.")

    #
    # =================== MAGIC METHODS ======================================
    #
    def __del__(self):

        self.hit(self.Inputs.disconnect)
        acts = self._tfsm_activeSck

        scks = (acts, self._tfsm_listenSck)
        scks = [sck for sck in scks if sck is not None]
        for sck in scks:
            try:
                sck.shutdown(socket.SHUT_RDWR)
            except socket.error:
                pass
        for sck in scks:
            try:
                sck.close()
            except socket.error:
                pass

        sp = super(TransportFSM, self)
        if hasattr(sp, "__del__"):
            try:
                sp.__del__()
            except NameError:
                log.exception("NameError calling super.__del__.")

    #
    # =================== INTERNAL ===========================================
    #
    @property
    def _tfsm_localAddress(self):
        for sck in (self._tfsm_activeSck, self._tfsm_listenSck):
            if sck is not None:
                return sck.getsockname()

        la = self.__dict__["_tfsm_localAddress"]
        return (tuple(la[:2]) if self._tfsm_family == socket.AF_INET else
                tuple(la))

    @property
    def _tfsm_localAddressHost(self):
        return self._tfsm_localAddress[0]

    @_tfsm_localAddressHost.setter
    def _tfsm_localAddressHost(self, val):
        self.__dict__["_tfsm_localAddress"][0] = val

    @property
    def _tfsm_localAddressPort(self):
        return self._tfsm_localAddress[1]

    @_tfsm_localAddressPort.setter
    def _tfsm_localAddressPort(self, val):
        la = self.__dict__["_tfsm_localAddress"][1] = val

    def _tfsm_dataAvailable(self, sck):
        """This method is registered when connected with the FSM's thread to
        be called when there is data available on the socket.
        """
        data, address = sck.recvfrom(self._tfsm_receiveSize)
        address = (
            address if address is not None else self._tfsm_remoteAddressTuple)
        datalen = len(data)

        if self._tfsm_remoteAddressTuple is None:
            # We have not yet learnt our interlocutor's address because we
            # are using datagram transport. Learn it.
            assert self.socketType == socket.SOCK_DGRAM
            sck.connect(address)
            self._tfsm_remoteAddressTuple = address

        if datalen > 0:
            log.info(" received from %r\n<<<<<\n%s\n<<<<<", address, data)

        self._tfsm_buffer.extend(data)

        if self._tfsm_byteConsumer is None:
            log.debug("No consumer; dumping data: %r.", self._tfsm_buffer)
            del self._tfsm_buffer[:]

        else:
            while len(self._tfsm_buffer) > 0:
                data_consumed = self._tfsm_byteConsumer(
                    bytes(self._tfsm_buffer))
                if data_consumed == 0:
                    log.debug("Consumer has used as much as it can.")
                    break
                log.debug("Consumer consumed %d more data.", data_consumed)
                del self._tfsm_buffer[:data_consumed]

        if datalen == 0:
            log.debug("Received 0 data: socket has demurely closed.")
            self.hit(self.Inputs.disconnect)