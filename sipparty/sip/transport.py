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

from sipparty import (util, fsm, FSM)

log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")
bytes = six.binary_type
itervalues = six.itervalues


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


class TransportFSM(FSM):
    """Abstract superclass for the listen and active transport FSMs."""

    DefaultType = socket.SOCK_STREAM
    DefaultFamily = socket.AF_INET

    #
    # =================== INSTANCE INTERFACE ==================================
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

    def __init__(self, **kwargs):

        for keydef_pair in (
                ("socketType", self.DefaultType),
                ("family", self.DefaultFamily),
                ("localAddress", [None, 0, 0, 0])):
            key = keydef_pair[0]
            if key in kwargs:
                self.__dict__["_tfsm_" + key] = kwargs[key]
                del kwargs[key]
            else:
                self.__dict__["_tfsm_" + key] = keydef_pair[1]

        assert ("asynchronous_timers" not in kwargs or
                kwargs["asynchronous_timers"])
        kwargs["asynchronous_timers"] = True

        super(TransportFSM, self).__init__(**kwargs)

    def transportError(self, msg="unknown error"):
        "We've hit an error."
        self._tfsm_errormsg = msg
        if self._tfsm_sck is not None:
            log.debug("Error: close listen socket")
            self._tfsm_sck.close()
            self._tfsm_sck = None

        log.error(msg)

    #
    # =================== MAGIC METHODS ======================================
    #
    def __del__(self):

        self.hit(self.Inputs.disconnect)

        sck = self._tfsm_sck
        try:
            sck.shutdown(socket.SHUT_RDWR)
        except socket.error:
            pass

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
    # =================== INTERNAL METHODS ====================================
    #
    @property
    def _tfsm_localAddress(self):
        for sck in (self._tfsm_sck, self._tfsm_sck):
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
        self.__dict__["_tfsm_localAddress"][1] = val


class ActiveTransportFSM(TransportFSM):
    """Controls a socket connection.
    """

    #
    # =================== CLASS INTERFACE ====================================
    #
    States = util.Enum(("connecting", "connected", "closed", "error"))
    Inputs = util.Enum(
        ("attemptConnect", "connectUp", "send", "disconnect", "error"))
    Actions = util.Enum(
        ("createConnect", "attemptConnect", "becomesConnected",
         "connectedSend", "becomesDisconnected", "transportError"))

    FSMDefinitions = {
        fsm.InitialStateKey: {
            Inputs.attemptConnect: {
                FSM.KeyNewState: States.connecting,
                FSM.KeyAction: Actions.createConnect,
                FSM.KeyStartThreads: Actions.becomesConnected
            }
        },
        States.connecting: {
            Inputs.error: {
                FSM.KeyNewState: States.error,
                FSM.KeyAction: Actions.transportError
            },
            Inputs.connectUp: {
                FSM.KeyNewState: States.connected,
                FSM.KeyAction: Actions.becomesConnected
            }
        },
        States.connected: {
            Inputs.send: {
                FSM.KeyNewState: States.connected,
                FSM.KeyAction: Actions.connectedSend
            },
            Inputs.disconnect: {
                FSM.KeyNewState: States.closed,
                FSM.KeyAction: Actions.becomesDisconnected
            },
            Inputs.error: {
                FSM.KeyNewState: States.error,
                FSM.KeyAction: Actions.transportError
            }
        },
        States.closed: {},
        States.error: {}
    }

    # Subclasses should override these so that a set of instances for their
    # particular subclass is not mixed with the generic transport set.
    ConnectedInstances = {}

    @classmethod
    def AddConnectedTransport(cls, tp):
        rkey = (tp.remoteAddressHost, tp.remoteAddressPort)
        typ = tp.socketType
        lkey = (tp.localAddressHost, tp.localAddressPort)
        cis1 = cls.ConnectedInstances

        for key1, key2, key3 in (rkey, typ, lkey), (rkey, lkey, typ):
            if key1 not in cis1:
                cis1[key1] = {}

            cis2 = cis1[key1]

            if key2 not in cis2:
                cis2[key2] = {}

            cis3 = cis2[key2]

            if key3 in cis3:
                raise KeyError(
                    "Transport to %r is already taken." % cis3[key3])
            cis3[key3] = tp

    @classmethod
    def GetConnectedTransport(cls, addr, port, typ=None):
        """Get a connected transport to the given address tuple.

        :param tuple key: Of the form (fromAddressTuple, fromPort, socketType,
        toAddressTuple, toPort)
        """
        assert typ is None, "Not yet implemented"
        key1 = (addr, port)
        cis1 = cls.ConnectedInstances
        if key1 in cis1:
            for dict1 in itervalues(cis1):
                for tp in itervalues(dict1):
                    log.debug("Got existing connected transport %r", tp)
                    return tp

        # No existing connected transport.
        tp = cls()
        tp.connect(key1)
        return tp

    @classmethod
    def NewWithConnectedSocket(cls, socket):
        assert 0

    #
    # =================== INSTANCE INTERFACE =================================
    #
    byteConsumer = util.DerivedProperty(
        "_tfsm_byteConsumer",
        lambda val: isinstance(val, collections.Callable))
    remoteAddress = util.DerivedProperty("_tfsm_remoteAddress")
    remoteAddressHost = util.DerivedProperty("_tfsm_remoteAddressHost")
    remoteAddressPort = util.DerivedProperty("_tfsm_remoteAddressPort")

    def __init__(self, **kwargs):

        for keydef_pair in (
                ("remoteAddress", None),
                ("byteConsumer", None)):
            key = keydef_pair[0]
            if key in kwargs:
                self.__dict__["_tfsm_" + key] = kwargs[key]
                del kwargs[key]
            else:
                self.__dict__["_tfsm" + key] = keydef_pair[1]

        super(ActiveTransportFSM, self).__init__(**kwargs)

        self._tfsm_receiveSize = 4096
        self._tfsm_timeout = 2
        self._tfsm_sck = None
        self._tfsm_buffer = bytearray()

    def connect(self, *args, **kwargs):
        self.hit(self.Inputs.connect, *args, **kwargs)
        self.waitForStateCondition(
            lambda state: state in (
                States.error, States.connecting, States.connected))

    def send(self, data):
        self.hit(self.Inputs.send, data)

    def disconnect(self):
        self.hit(self.Inputs.disconnect)
        self.waitForStateCondition(
            lambda state: state in (States.error, States.disconnected))

    #@fsm.block_until_states((States.disconnected))
    #def reset(self):
    #    self.hit(self.Inputs.reset)

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

        if len(addr_tuple) < explen:
            self.hit(self.Inputs.error, "Bad address %r for %r socket." %
                     (addr_tuple, SockFamilyName(fam)))
            return
        addr_tuple = addr_tuple[:2]

        try:
            self._tfsm_sck = GetBoundSocket(fam, typ, adr)
        # Need to add proper exception handling for socket errors here.
        except:
            log.error("Exception hit getting bound socket for connection.")
            self.hit(self.Inputs.error)

        self._tfsm_remoteAddress = addr_tuple

    def becomesConnected(self):
        "Called when the transport becomes connected"
        self.AddConnectedTransport(self)
        self.addFDSource(self._tfsm_sck,
                         util.WeakMethod(self, "_tfsm_dataAvailable"))

    def becomesDisconnected(self):
        "Called when the transport goes down."
        self.rmFDSource(self._tfsm_sck)
        for sck in (self._tfsm_sck, self._tfsm_sck):
            if sck is not None:
                sck.close()
        self._tfsm_sck = None
        self._tfsm_sck = None

    def connectedSend(self, data):
        "Send some data."
        datalen = len(data)
        sck = self._tfsm_sck

        try:
            sent_bytes = sck.send(data)
            prot_log.info("send\n>>>>>\n%s\n>>>>>", data)
        except socket.error:
            log.error("Exception sending bytes to %r", sck.getsockname())
            raise

        if sent_bytes != datalen:
            self.error("Failed to send %d bytes of data." %
                       (datalen - sent_bytes))

    #
    # =================== THREADS ============================================
    #
    def attemptConnect(self):
        "Attempt to connect out."
        log.debug("Attempt to connect to %r.", self._tfsm_remoteAddress)
        sck = self._tfsm_sck
        if sck is None:
            log.debug("Create socket failed, so nothing to do.")
            return

        family = self.family
        sck_type = self.socketType
        address = self._tfsm_localAddress
        remote_address = self._tfsm_remoteAddress

        try:
            self._tfsm_sck.connect(self._tfsm_remoteAddress)
        except Exception as exc:
            self.hit(
                self.Inputs.error,
                "Exception connecting to %r: %r." %
                (self._tfsm_remoteAddress, exc))
            return

        log.debug("Attempt connect done.")
        self.hit(self.Inputs.connected)

    #
    # =================== INTERNAL ===========================================
    #
    @property
    def _tfsm_remoteAddressHost(self):
        return self.remoteAddress[0]

    @property
    def _tfsm_remoteAddressPort(self):
        return self.remoteAddress[1]

    def _tfsm_dataAvailable(self, sck):
        """This method is registered when connected with the FSM's thread to
        be called when there is data available on the socket.
        """
        data, address = sck.recvfrom(self._tfsm_receiveSize)
        address = (
            address if address is not None else self._tfsm_remoteAddress)
        datalen = len(data)

        if self._tfsm_remoteAddress is None:
            # We have not yet learnt our interlocutor's address because we
            # are using datagram transport. Learn it.
            assert self.socketType == socket.SOCK_DGRAM
            sck.connect(address)
            self._tfsm_remoteAddress = address

        if datalen > 0:
            prot_log.info(" received from %r\n<<<<<\n%s\n<<<<<", address, data)

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


class ListenTransportFSM(TransportFSM):
    #
    # =================== CLASS INTERFACE ====================================
    #
    States = util.Enum(
        ("startListen",
         "listening",
         "closed",
         "error"))
    Inputs = util.Enum(
        ("listen", "listenup", "accept", "close", "error"))
    Actions = util.Enum(
        ("createListen", "startListening", "accept", "becomesDisconnected",
         "transportError"))
    FSMDefinitions = {
        fsm.InitialStateKey: {
            Inputs.listen: {
                FSM.KeyNewState: States.startListen,
                FSM.KeyAction: Actions.createListen,
                #FSM.KeyStartThreads: Actions.startListening
            }
        },
        States.startListen: {
            Inputs.listenup: {
                FSM.KeyNewState: States.listening,
                FSM.KeyStartThreads: (Actions.startListening,)
            },
            Inputs.error: {
                FSM.KeyNewState: States.error,
                FSM.KeyAction: Actions.transportError
            }
        },
        States.listening: {
            Inputs.accept: {
                FSM.KeyNewState: States.listening,
                FSM.KeyAction: Actions.accept
            }
        },
        States.closed: {},
        States.error: {}
    }

    # Subclasses should override these so that a set of instances for their
    # particular subclass is not mixed with the generic transport set.
    ConnectedInstances = {}
    ListeningInstances = {}

    @classmethod
    def AddListeningTransport(cls, tp):
        lkey = (tp.localAddressHost, tp.localAddressPort)
        lis = cls.ListeningInstances

        if lkey in lis:
            raise KeyError(
                "Transport already listening on %r." % (lkey,))

        lis[lkey] = tp

    @classmethod
    def GetListeningTransport(cls, addr, port):
        """Get a Listening transport to the given address tuple.

        :param bytes addr: Address (hostname, IPv6 / IPv4) on which to listen.
        :param int port: port to listen on.
        """
        key = (addr, port)
        lis = cls.ListeningInstances
        if key in lis:
            return lis[key]

        # No existing Listening transport.
        tp = cls()
        tp.localAddressHost = addr
        tp.localAddressPort = port
        tp.listen()
        AddListeningTransport(tp)
        return tp

    #
    # =================== INSTANCE INTERFACE =================================
    #
    def __init__(self, **kwargs):

        # The transport FSM is a root level independent FSM that schedules
        # its own work on a background thread, and to do this it uses the
        # asynchronous_timers feature of the FSM class.
        assert ("asynchronous_timers" not in kwargs or
                kwargs["asynchronous_timers"])
        kwargs["asynchronous_timers"] = True

        for keydef_pair in (
                ("acceptConsumer", None),):
            key = keydef_pair[0]
            if key in kwargs:
                self.__dict__["_tfsm_" + key] = kwargs[key]
                del kwargs[key]
            else:
                self.__dict__["_tfsm" + key] = keydef_pair[1]

        super(ListenTransportFSM, self).__init__(**kwargs)

        self._tfsm_remoteAddress = None

        self._tfsm_receiveSize = 4096
        self._tfsm_timeout = 2

        self._tfsm_sck = None
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

    def listen(self, host=None, port=None):
        if host is not None:
            self.localAddressHost = host
        if port is not None:
            self.localAddressPort = port
        self.hit(self.Inputs.listen)
        self.waitForStateCondition(
            lambda state: state != fsm.InitialStateKey)

    def send(self, data):
        self.hit(self.Inputs.send, data)

    def disconnect(self):
        self.hit(self.Inputs.disconnect)
        self.waitForStateCondition(
            lambda state: state != ListenTransportFSM.States.listening)

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
    def createListen(self):
        try:
            self._tfsm_sck = GetBoundSocket(
                self.family, self.socketType, self._tfsm_localAddress)
        except Exception as exc:
            log.exception("Exception getting passive socket.")
            self.hit(self.Inputs.error,
                     "Exception getting passive socket: %r." % exc)
            return

        # Listen if it's a stream.
        if self._tfsm_sck.type == socket.SOCK_STREAM:
            log.debug("Listening for connections.")
            self._tfsm_sck.listen(0)

        self._tfsm_sck.settimeout(self._tfsm_acceptSocketTimeout)
        log.info(
            "Passive socket created on %r.",
            self._tfsm_sck.getsockname())

        log.debug("passive listen address: %r", self.localAddress)
        self.hit(self.Inputs.listenup)

    def becomesDisconnected(self):
        "Called when the transport goes down."
        sck = self._tfsm_sck
        self.rmFDSource(sck)
        if sck is not None:
            sck.close()
        self._tfsm_sck = None

    #
    # =================== THREADS ============================================
    #
    def startListening(self):

        lsck = self._tfsm_sck

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
            self._tfsm_sck = self._tfsm_sck
            self.hit(self.Inputs.connected)
            return

        # TCP socket.
        log.debug("Stream sockets: try and accept.")

        try:
            conn, addr = lsck.accept()
            self._tfsm_sck = conn
            self._tfsm_remoteAddress = addr
            log.info("Connection accepted from %r.",
                     self._tfsm_remoteAddress)
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
        acts = self._tfsm_sck

        scks = (acts, self._tfsm_sck)
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
