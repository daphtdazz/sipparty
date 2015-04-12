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
import socket
import threading
import time
import logging
import _util
import fsm

log = logging.getLogger(__name__)


class BadNetwork(Exception):
    pass


def GetPassiveSocket(name=None, family=0, socktype=0, port=None):

    if name is None:
        name = socket.gethostname()

    # family e.g. AF_INET / AF_INET6
    # socktype e.g. SOCK_STREAM
    # Just grab the first addr info if we haven't
    log.debug("getaddrinfo addr:%r port:%r family:%r socktype:%r",
              name, port, family, socktype)
    addrinfos = socket.getaddrinfo(name, port, family, socktype)

    for family, socktype, proto, _, (sockaddr, _) in addrinfos:
        if (family in (socket.AF_INET, socket.AF_INET6) and
                socktype in (socket.SOCK_STREAM, socket.SOCK_DGRAM)):
            break
    else:
        raise BadNetwork("Could not find an address to bind to %r." % name)

    ssocket = socket.socket(family, socktype)

    def port_generator():
        yield 5060  # Always try 5060 first.
        for ii in range(15060, 0x10000):
            yield ii

    for port in port_generator():
        try:
            ssocket.bind((sockaddr, port))
            break
        except socket.error:
            pass
    else:
        raise BadNetwork(
            "Couldn't get a port for address {sockaddr}.".format(
                **locals()))

    if socktype == socket.SOCK_STREAM:
        ssocket.listen(0)

    return ssocket


class TransportFSM(fsm.FSM):
    """Controls a socket connection
    """

    States = _util.Enum(
        ("disconnected",
         "listening",
         "connecting",
         "connected",
         "error"))
    Inputs = _util.Enum(
        ("connect", "listen", "connected", "accepted", "disconnect", "error",
         "reset"))
    Actions = _util.Enum(
        ("attemptConnect", "becomesDisconnected", "createListen",
         "startListening",
         "accepted", "error"))

    @classmethod
    def AddClassTransitions(cls):

        S = cls.States
        I = cls.Inputs
        A = cls.Actions

        # Transitions when connecting out.
        cls.addTransition(  # Start the connect process.
            S.disconnected, I.connect, S.connecting,
            action=None,
            start_threads=[A.attemptConnect])
        cls.addTransition(  # Error cases.
            S.connecting, I.error, S.error,
            action=A.error)
        cls.addTransition(  # Connect succeeds.
            S.connecting, I.connected, S.connected,
            action=None,
            join_threads=[A.attemptConnect])

        # Disconnect.
        cls.addTransition(
            S.connected, I.disconnect, S.disconnected,
            action=A.becomesDisconnected)

        # Transitions when being connected to.
        cls.addTransition(  # Start listening and waiting for an accept.
            S.disconnected, I.listen, S.listening,
            action=A.createListen,
            start_threads=[A.startListening])
        cls.addTransition(  # Error.
            S.listening, I.error, S.error,
            action=A.error)
        cls.addTransition(  # Successful listen.
            S.listening, I.accepted, S.connected,
            action=A.accepted,
            join_threads=[A.startListening])

        # Error in error and reset from an error.
        # cls.addTransition(S.error, I.error, S.error)
        cls.addTransition(
            S.error, I.reset, S.disconnected,
            join_threads=[A.startListening, A.attemptConnect])

        # Same transition for disconnected.
        cls.setState(S.disconnected)

    def __init__(self, *args, **kwargs):

        # The transport FSM is a root level independent FSM that schedules
        # its own work on a background thread, and to do this it uses the
        # asynchronous_timers feature of the FSM class.
        assert ("asynchronous_timers" not in kwargs or
                kwargs["asynchronous_timers"])
        kwargs["asynchronous_timers"] = True
        super(TransportFSM, self).__init__(*args, **kwargs)

        self._tfsm_family = None
        self._tfsm_type = None
        self._tfsm_address = None
        self._tfsm_remoteAddress = None
        self._tfsm_remotePort = None

        self._tfsm_timeout = 2

        self._tfsm_listenSck = None
        self._tfsm_activeSck = None

        # BSD (Mac OS X anyway) seems not to propagate an error to an accept
        # call on a socket if you close it from a different thread. So need
        # to use non-blocking sockets so that the accept loop can keep
        # checking whether the socket is still valid.
        self._tfsm_acceptSocketTimeout = 0.1

    @property
    def family(self):
        return self._tfsm_family

    @family.setter
    def family(self, value):
        if value not in (socket.AF_INET, socket.AF_INET6):
            raise ValueError("Bad socket family %r." % value)
        self._tfsm_family = value

    @property
    def type(self):
        return self._tfsm_type

    @type.setter
    def type(self, value):
        if value not in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            raise ValueError("Bad socket type %r." % value)
        self._tfsm_type = value

    def block_until_states(states):
        "This is a descriptor, so don't call it as a method."

        def buse_desc(method):
            def block_until_states_wrapper(self, *args, **kwargs):
                state_now = self.state
                method(self, *args, **kwargs)

                end_states = states
                time_start = time.clock()
                time_now = time_start
                while self.state not in end_states:
                    if time_now - time_start > self._tfsm_timeout:
                        self.hit(self.States.error)
                        new_end_states = (self.States.error,)
                        if end_states == new_end_states:
                            # Ahh must do proper exceptions!
                            raise Exception(
                                "help failed to enter error state.")
                        end_states = new_end_states
                        time_start = time_now

                    time.sleep(0.00001)
                    time_now = time.clock()

                if self.state not in end_states:
                    # Ahh must do proper exceptions!
                    raise Exception("Timeout reaching end state.")
            return block_until_states_wrapper
        return buse_desc

    # !!! These could be improved.
    @block_until_states((States.error, States.listening))
    def listen(self):
        self.hit(self.Inputs.listen)

    @block_until_states((States.error, States.connected))
    def connect(self):
        self.hit(self.Inputs.connect)

    @block_until_states((States.error, States.disconnected))
    def disconnect(self):
        self.hit(self.Inputs.disconnect)

    @block_until_states((States.disconnected))
    def reset(self):
        self.hit(self.Inputs.reset)

    #
    # FSM ACTIONS
    #

    def createListen(self):
        family = self.family
        sck_type = self.type
        address = self._tfsm_address
        remote_address = self._tfsm_remoteAddress

        if not self._trnsfsm_checkLocalConfigIsOK(family, sck_type, address):
            # CheckLocalConfigIsOK respins with error if it is not.
            return

        try:
            self._tfsm_listenSck = GetPassiveSocket(address, family, sck_type)
        except Exception as exc:
            log.exception("Exception getting passive socket.")
            self.hit(self.Inputs.error,
                     "Exception getting passive socket: %r." % exc)
            return

        self._tfsm_listenSck.settimeout(self._tfsm_acceptSocketTimeout)
        log.debug("Listen socket created %r.", self._tfsm_listenSck)

    def becomesConnected(self):
        "Called when the transport becomes connected"
        self.addFDSource(self._tfsm_activeSck, self.dataAvailable)

    def becomesDisconnected(self):
        "Called when the transport goes down."
        self.rmFDSource(self, self._tfsm_activeSck)
        actsck = self._tfsm_activeSck
        self._tfsm_activeSck = None
        del actsck

    def accepted(self):
        "We just accepted an inbound connection."

    def dataAvailable(self, sck):
        """This method is registered when connected with the FSM's thread to
        be called when there is data available on the socket.
        """

    def error(self, msg="unknown error"):
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

        log.error("Error in transport: %r.", msg)

    # Asynchronous actions.
    def attemptConnect(self):
        "Attempt to connect out."
        family = self.family
        sck_type = self.type
        address = self._tfsm_address
        remote_address = self._tfsm_remoteAddress

        if not self._trnsfsm_checkLocalConfigIsOK(family, sck_type, address):
            return

        # Finish the connect out FSM side, and move on to the accept.

    def startListening(self):

        if self._tfsm_listenSck.type == socket.SOCK_DGRAM:
            raise ValueError("DGRAM socket (UDP) support not implemented.")

        log.debug("STREAM socket so block to accept a connection.")

        while True:
            lsck = self._tfsm_listenSck
            if lsck is None:
                log.debug("Listen has been cancelled.")
                break

            try:
                conn, addr = lsck.accept()
                log.debug("Connection accepted from %r.", addr)
                self.hit(self.Inputs.accepted, conn, addr)
                break
            except socket.timeout:
                continue
            except Exception as exc:
                log.debug("Exception selecting listen socket", exc_info=True)
                self.hit(self.Inputs.error,
                         "Exception selecting listen socket %r." % exc)
                break

    #
    # INTERNAL METHODS.
    #
    def _trnsfsm_checkLocalConfigIsOK(self, family, sck_type, address):
        if family is None:
            self.hit(self.Inputs.error,
                     "No INET family specified to connect to.")
            return False

        if sck_type is None:
            self.hit(self.Inputs.error,
                     "No socket type (STREAM / DGRAM) specified.")
            return False

        return True

    def _trnsfsm_checkRemoteConfigIsOK(sellf, address, port):
        pass
