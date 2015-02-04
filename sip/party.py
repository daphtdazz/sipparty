""":Copyright: David Park 2015

Implements the `Party` object.
"""
import socket

import prot
import components
import defaults
from message import Message
import copy
import pdb

__all__ = ('Party',)


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


class PortManager(object):

    _singleton = None

    def __new__(cls, *args, **kwargs):
        if PortManager._singleton is None:
            PortManager._singleton = super(PortManager, cls).__new__(
                cls, *args, **kwargs)

        return PortManager._singleton

    def find_port_and_bind(self, host=None, family=0, socktype=0,
                           address=None):

        if host is None:
            host = socket.gethostname()

        # family e.g. AF_INET / AF_INET6
        # socktype e.g. SOCK_STREAM
        # proto e.g.
        # Just grab the first addr info if we haven't
        addrinfos = socket.getaddrinfo(host, None, family)

        for family, socktype, proto, _, (sockaddr, _) in addrinfos:
            if (family in (socket.AF_INET, socket.AF_INET6) and
                    socktype in (socket.SOCK_STREAM, socket.SOCK_DGRAM)):
                break
        else:
            raise BadNetwork("Could not find a public address to connect to")

        family_name = SockFamilyName(family)
        socktype_name = SockTypeName(socktype)
        ssocket = socket.socket(family, socktype)

        def port_generator():
            yield 5060
            for ii in range(15060, 16060):
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
            ssocket.listen(1)

        print("{family_name}:{socktype_name}:{sockaddr}:{port}".format(
            **locals()))
        return ssocket


def NewAOR():
    newaor = defaults.AORs.pop(0)
    defaults.AORs.append(newaor)
    return newaor


class BindNeeder(object):

    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError("Class {0!r} has no attribute {1!r}".format(
                owner.__name__, self.__name__))
        if self.name not in instance.__dict__:
            instance.bind()

        return instance.__dict__[self.name]

    def __set__(self, instance, value):
        instance.__dict__[self.name] = value


class Party(object):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    def __init__(self, username=None, host=None, displayname=None):
        """Create the party.
        """
        self.sentmessages = []
        self.rcvdmessages = []
        self.aor = NewAOR()

        # These will be determined later.

    port = BindNeeder("port")
    address = BindNeeder("address")
    sockfamily = BindNeeder("sockfamily")
    socktype = BindNeeder("socktype")

    def connect(self, hostname, port, sockfamily, socktype):
        self.active_socket = socket.socket(sockfamily, socktype)
        self.active_socket.connect((hostname, port))

    def bind(self):
        """
        """
        pm = PortManager()
        self.passive_socket = pm.find_port_and_bind()
        self.address, self.port = self.passive_socket.getsockname()
        self.sockfamily = self.passive_socket.family
        self.socktype = self.passive_socket.type

    # Send methods.
    def register(self):
        """Register the party with a server."""

    def invite(self, callee):
        """Start a call."""
        invite = Message.invite()
        invite.startline.uri.aor = copy.deepcopy(callee.aor)
        invite.fromheader.value.value.uri.aor = copy.deepcopy(self.aor)
        invite.viaheader.value.transport = SockTypeName(callee.socktype)
        self.connect(
            callee.address, callee.port, callee.sockfamily, callee.socktype)
        self.active_socket.sendall(str(invite))

    def receiveMessage(self):
        if hasattr(self, "active_socket"):
            sock = self.active_socket
        else:
            sock = self.passive_socket

        if sock.type == socket.SOCK_STREAM:
            assert 0
        else:
            data, addr = sock.recvfrom(4096)
        return data

    def respond(self, code):
        """Send a SIP response code."""
        msg = self.receiveMessage()

    # Receiving methods.
    def receive_response(self, code):
        """Receive a response code after a request."""
