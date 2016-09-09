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
from __future__ import absolute_import

from collections import Callable
from copy import copy
import logging
from numbers import Integral
import re
from six import iteritems
import socket  # TODO: should remove and rely on from socket import ... below.
from socket import (
    AF_INET, AF_INET6, error as socket_error, getaddrinfo, gethostname,
    SHUT_RDWR, socket as socket_class, SOCK_STREAM, SOCK_DGRAM)
from weakref import WeakValueDictionary
from .classmaker import classbuilder
from .deepclass import (dck, DeepClass)
from .fsm import (RetryThread)
from .vb import ValueBinder
from .util import (
    abytes, AsciiBytesEnum, astr, bglobals_g,
    DerivedProperty, Enum, Singleton, Retainable,
    TupleRepresentable, TwoCompatibleThree, WeakMethod, WeakProperty)


def bglobals():
    return bglobals_g(globals())

SOCK_TYPES = Enum((SOCK_STREAM, SOCK_DGRAM))
SOCK_TYPES_NAMES = AsciiBytesEnum((b"SOCK_STREAM", b"SOCK_DGRAM"))
SOCK_TYPE_IP_NAMES = AsciiBytesEnum((b"TCP", b"UDP"))
SOCK_FAMILIES = Enum((AF_INET, AF_INET6))
SOCK_FAMILY_NAMES = AsciiBytesEnum((b"IPv4", b"IPv6"))
DEFAULT_SOCK_FAMILY = AF_INET
log = logging.getLogger(__name__)
prot_log = logging.getLogger(__name__ + ".messages")

# RFC 2373 IPv6 address format definitions.
digitrange = b"0123456789"
DIGIT = b"[%(digitrange)s]" % bglobals()
hexrange = b"%(digitrange)sabcdefABCDEF" % bglobals()
HEXDIG = b"[%(hexrange)s]" % bglobals()
hex4 = b"%(HEXDIG)s{1,4}" % bglobals()
IPv4address = b"%(DIGIT)s{1,3}(?:[.]%(DIGIT)s{1,3}){3}" % bglobals()

# IPv6address is a bit complicated. This expression is to ensure we match all
# possibilities with restricted length, and do a maximal match each time which
# doesn't happen if we slavishly follow the ABNF in RFC 2373, which is a bit
# rubbish and doesn't seem to care about the length of the address (!).
col_hex4 = b':%(hex4)s' % bglobals()
col_hex4_gp = b'(?:%(col_hex4)s)' % bglobals()
IPv6address = (
    # May start with double colon such as ::, ::1, ::fe80:1:2 etc.
    b'(?:::(?:%(hex4)s%(col_hex4_gp)s{,6})?|'  # Net one '('...
    # Or there is a double colon somewhere inside... but we want to make sure
    # we match the double colon immediately, without the regex engine having to
    # track back, so do each option explicitly.
    b'%(hex4)s(?:::(?:%(hex4)s%(col_hex4_gp)s{,5})?|'  # (
    b'%(col_hex4_gp)s(?:::(?:%(hex4)s%(col_hex4_gp)s{,4})?|'  # (
    b'%(col_hex4_gp)s(?:::(?:%(hex4)s%(col_hex4_gp)s{,3})?|'  # (
    b'%(col_hex4_gp)s(?:::(?:%(hex4)s%(col_hex4_gp)s{,2})?|'  # (
    b'%(col_hex4_gp)s(?:::(?:%(hex4)s%(col_hex4_gp)s{,1})?|'  # (
    b'%(col_hex4_gp)s(?:::(?:%(hex4)s)?|'  # (
    b'%(col_hex4_gp)s(?:::|'  # (
    b'%(col_hex4_gp)s'
    b'))))))))' % bglobals())

IPaddress = b"(?:(%(IPv4address)s)|(%(IPv6address)s))" % bglobals()
port = b"%(DIGIT)s+" % bglobals()

# Some pre-compiled regular expression versions.
hex4_re = re.compile(b'(' + hex4 + b')')
IPv4address_re = re.compile(IPv4address)
IPv4address_only_re = re.compile(IPv4address + b'$')
IPv6address_re = re.compile(IPv6address)
IPv6address_only_re = re.compile(IPv6address + b'$')
IPaddress_re = re.compile(IPaddress)
IPaddress_only_re = re.compile(IPaddress + b'$')

first_unregistered_port = 49152
next_port = first_unregistered_port


class Name(object):
    def __repr__(self):
        return __name__ + '.' + self.__class__.__name__

NameAll = type(
    'NameAll', (Name,), {
        '__doc__': (
            'Use this singleton object in your call to listen_for_me to '
            'indicate that you wish to listen on all addresses.')
    }
)()
NameLANHostname = type(
    'NameLANHostname', (Name,), {
        '__doc__': (
            'Use this singleton object in your call to listen_for_me to '
            'indicate that you wish to listen on an address you have '
            'exposed on the Local Area Network.')
    }
)()
NameLoopbackAddress = type(
    'NameLoopbackAddress', (Name,), {
        '__doc__': (
            'Use this singleton object in your call to listen_for_me to '
            'indicate that you wish to listen on an address you have '
            'exposed on the Local Area Network.')
    }
)()
SendFromAddressNameAny = type(
    'SendFromAddressNameAny', (Name,), {
        '__doc__': (
            'Use this singleton object in your call to '
            'get_send_from_address to '
            'indicate that you wish to send from any routable '
            'local address.')
    }
)()
SpecialNames = set((
    NameAll, NameLANHostname, NameLoopbackAddress, SendFromAddressNameAny
))


def address_as_tuple(addr_name):

    bname = abytes(addr_name)
    fam = IPAddressFamilyFromName(bname, exact=True)
    if fam is None:
        raise ValueError('%s is not an IP address' % (addr_name,))

    if fam == AF_INET:
        return _ipv4_address_as_tuple(bname)

    assert fam == AF_INET6
    return _ipv6_address_as_tuple(bname)


def _ipv4_address_as_tuple(bname):
    return tuple(int(num) for num in bname.split(b'.'))


def _ipv6_address_as_tuple(bname):

    nums_list = []
    zero_squelch_ind = None
    for gp in hex4_re.split(bname):
        if not gp:
            continue

        if gp == b':':
            continue
        if gp == b'::':
            assert zero_squelch_ind is None, (
                'unexpected second zero squelcher (::) in ipv6 address '
                'lookalike address %s' % (bname,))
            zero_squelch_ind = len(nums_list)
            continue

        nums_list.append(int(gp, base=16))

    if zero_squelch_ind is None:
        assert len(nums_list) == 8, (
            'bad length (not 8) for expanded ipv6 address: %s' % (
                nums_list,))
        return tuple(nums_list)

    return tuple(
        nums_list[:zero_squelch_ind] +
        [0] * (8 - len(nums_list)) +
        nums_list[zero_squelch_ind:])


def AllAddressesFromFamily(sock_family):
    if sock_family == AF_INET:
        return '0.0.0.0'

    if sock_family == AF_INET6:
        return '::'

    return None


def default_hostname():
    # This is partly here so we can patch it in UTs.
    return gethostname()


def IPAddressFamilyFromName(name, exact=False):
    """Returns the family of the IP address passed in in name, or None if it
    could not be determined.
    :param name:
        The IP address or domain name to try and work out the family of.
    :returns: None, AF_INET or AF_INET6.
    """
    if name is None or name in SpecialNames:
        return None
    name = abytes(name)

    try:
        if not exact:
            mo = IPaddress_re.match(name)
        else:
            mo = IPaddress_only_re.match(name)
    except (TypeError, ValueError):
        log.error('Bad name: %r', name)
        raise

    if mo is None:
        return None

    if mo.group(1) is not None:
        return AF_INET

    assert mo.group(2) is not None
    return AF_INET6


def is_null_address(name):
    return all(num == 0 for num in (address_as_tuple(name) or [1]))


def IsSpecialName(name):
    return name in SpecialNames


def IsValidPortNum(port):
    if not isinstance(port, Integral):
        # We only have to do this for python 2.7, python 3 doesn't allow
        # comparison of arbitrary objects with numbers.
        raise TypeError('Port %r is not Integral', port)
    return 0 < port <= 0xffff


def IsValidTransportName(name):
    return isinstance(name, str) or IsSpecialName(name)


def LoopbackAddressFromFamily(sock_family):
    if sock_family == AF_INET:
        return '127.0.0.1'

    if sock_family == AF_INET6:
        return '::1'

    return None


def UnregisteredPortGenerator(port_filter=None):
    global next_port
    start_port = next_port
    while True:
        if port_filter is None or port_filter(next_port):
            yield next_port
        next_port += 1
        if next_port > 0xffff:
            next_port = first_unregistered_port
        if next_port == start_port:
            break


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

    def __str__(self):
        sp_str_gt = getattr(super(BadNetwork, self), '__str__', None)
        if sp_str_gt is not None:
            sp_str = sp_str_gt()
        else:
            sp_str = 'BadNetwork'

        return "%s. Socket error: %s" % (sp_str, self.socketError)


class SocketInUseError(TransportException):
    pass


def SockFamilyName(family):
    return SOCK_FAMILY_NAMES[SOCK_FAMILIES.index(family)]


def SockTypeName(socktype):
    if socktype == SOCK_STREAM:
        return SOCK_TYPE_IP_NAMES.TCP
    if socktype == SOCK_DGRAM:
        return SOCK_TYPE_IP_NAMES.UDP

    raise TypeError('%r is not one of %r' % (socktype, SOCK_TYPES))


def SockTypeFromName(socktypename):
    if socktypename == SOCK_TYPE_IP_NAMES.TCP:
        return SOCK_STREAM
    if socktypename == SOCK_TYPE_IP_NAMES.UDP:
        return SOCK_DGRAM
    assert socktypename in SOCK_TYPE_IP_NAMES


def GetBoundSocket(family, socktype, address, port_filter=None):
    """
    :param int family: The socket family, one of AF_INET or AF_INET6.
    :param int socktype: The socket type, SOCK_STREAM or SOCK_DGRAM.
    :param tuple address: The address / port pair, like ("localhost", 5060).
    Pass None for the address or 0 for the port to choose a locally exposed IP
    address if there is one, and an arbitrary free port.
    """

    if family is None:
        family = 0
    if socktype is None:
        socktype = 0
    if family != 0 and family not in SOCK_FAMILIES:
        raise ValueError('Invalid family %d: not 0 or one of %r' % (
            SOCK_FAMILY_NAMES,))
    assert socktype in (0, SOCK_STREAM, SOCK_DGRAM)

    address_list = list(address)

    # family e.g. AF_INET / AF_INET6
    # socktype e.g. SOCK_STREAM
    # Just grab the first addr info if we haven't
    log.debug("GetBoundSocket addr:%r port:%r family:%r socktype:%r...",
              address_list[0], address_list[1], family, socktype)

    if address_list[0] is NameAll:
        if family != 0:
            address_list[0] = AllAddressesFromFamily(family)
        else:
            # We've been asked for the 'all' address, but we haven't been told
            # a family, so we just have to pick one, so pick AF_INET!
            address_list[0] = AllAddressesFromFamily(DEFAULT_SOCK_FAMILY)
            family = DEFAULT_SOCK_FAMILY

    gai_tuple = (address_list[0], address_list[1], family, socktype)
    addrinfos = getaddrinfo(*gai_tuple)
    if len(addrinfos) == 0:
        raise BadNetwork(
            "Could not find an address to bind to for %r." % address, None)

    log.debug("Using address %r.", addrinfos[0])
    log.detail("  %r", addrinfos)

    _family, _socktype, _proto, _canonname, ai_address = addrinfos[0]
    ssocket = socket_class(_family, _socktype)

    # Clean the address, which on some devices if it's IPv6 will have the name
    # of the interface appended after a % character.
    if _family == AF_INET6:
        old_name = ai_address[0]
        mo = IPv6address_re.match(abytes(old_name))
        ai_address = (mo.group(0),) + ai_address[1:]
        if old_name != ai_address[0]:
            log.debug('Cleaned IPv6address: %r -> %r', old_name, ai_address[0])

    def port_generator():
        if ai_address[1] != 0:
            # The port was specified.
            log.debug("Using just passed port %d", ai_address[1])
            yield ai_address[1]
            return

        # Guess a port from the unregistered range.
        for port in UnregisteredPortGenerator(port_filter):
            yield port

    socketError = None
    max_retries = 10
    attempts = 0
    bind_addr = None
    for port in port_generator():
        try:
            # TODO: catch specific errors (e.g. address in use) to bail
            # immediately rather than inefficiently try all ports.

            if _family == AF_INET:
                bind_addr = (ai_address[0], port)
            else:
                bind_addr = (ai_address[0], port) + ai_address[2:]
            ssocket.bind(bind_addr)
            log.debug(
                'Bind socket to %r, result %r', bind_addr,
                ssocket.getsockname())
            socketError = None
            break

        except socket_error as _se:
            log.debug("Socket error on %r", bind_addr)
            socketError = _se
            attempts += 1

        except socket.gaierror as _se:
            log.debug("GAI error on %r", bind_addr)
            socketError = _se
            break

        except OSError as exc:
            log.error('%r', exc)
            raise

        if attempts == max_retries:
            log.error('Hit max retries: %d', max_retries)
            break

    if socketError is not None:
        raise BadNetwork(
            "Couldn't bind to address %r (request was for %r), tried %d "
            "ports" % (
                bind_addr, address, attempts),
            socketError)

    log.debug("Socket bound to %r type %r", ssocket.getsockname(), _family)
    return ssocket


@classbuilder(
    bases=(
        DeepClass('_laddr_', {
            'port': {dck.check: lambda x: x == 0 or IsValidPortNum(x)},
            'sock_family': {dck.check: lambda x: x in SOCK_FAMILIES},
            'sock_type': {dck.check: lambda x: x in SOCK_TYPES},
            'name': {
                dck.check: lambda x: IsValidTransportName(x)},
            'flowinfo': {dck.check: lambda x: isinstance(x, Integral)},
            'scopeid': {dck.check: lambda x: isinstance(x, Integral)},
            'port_filter': {dck.check: lambda x: isinstance(x, Callable)}}),
        ValueBinder,
        TupleRepresentable))
class ListenDescription:

    @classmethod
    def description_from_socket(cls, sck):
        sname = sck.getsockname()

        addr = cls(
            name=sname[0], sock_family=sck.family, sock_type=sck.type,
            port=sname[1], flowinfo=None if len(sname) == 2 else sname[2],
            scopeid=None if len(sname) == 2 else sname[3])
        return addr

    def deduce_missing_values(self):

        if self.sock_family is None:
            if self.name is not None:
                self.sock_family = IPAddressFamilyFromName(self.name)

        if self.sock_family == AF_INET6:
            for ip6_attr in ('flowinfo', 'scopeid'):
                if getattr(self, ip6_attr) is None:
                    setattr(self, ip6_attr, 0)

    @property
    def sockname_tuple(self):
        name = self.name

        if self.name is SendFromAddressNameAny:
            name = ''
        elif self.name is NameLoopbackAddress:
            name = None
        elif self.name is NameLANHostname:
            name = default_hostname()
        else:
            name = self.name

        if self.port is None:
            port = 0
        else:
            port = self.port

        if self.sock_family == AF_INET:
            return (name, port)
        fi = self.flowinfo or 0
        scid = self.scopeid or 0
        return (name, port, fi, scid)

    def tupleRepr(self):
        return (
            self.__class__, self.sock_family, self.sock_type, self.port,
            self.name)

    def listen(self, data_callback, transport):
        """Return a SocketProxy using the ListenDescription's parameters, or
        raise an exception if not possible.
        """
        lsck = GetBoundSocket(
            self.sock_family, self.sock_type, self.sockname_tuple,
            self.port_filter)

        laddr = self.description_from_socket(lsck)

        log.info('New listen socket %s', laddr)

        return SocketProxy(
            local_address=laddr, socket=lsck, data_callback=data_callback,
            transport=transport)

    def __str__(self):
        if self.sock_family == AF_INET6:
            return '[{self.name}]:{self.port} ({sock_type})'.format(
                self=self, sock_type=astr(SockTypeName(self.sock_type)))

        if self.sock_family == AF_INET:
            return '{self.name}:{self.port} ({sock_type})'.format(
                self=self, sock_type=astr(SockTypeName(self.sock_type)))

        return "'{self.name}' (unknown type), port: {self.port}".format(
            self=self)


class ConnectedAddressDescription(
        DeepClass('_cad_', {
            'remote_name': {
                dck.check: lambda x: IsValidTransportName(x)},
            'remote_port': {dck.check: IsValidPortNum},
        }, recurse_repr=True),
        ListenDescription):

    @classmethod
    def description_from_socket(cls, sck):
        cad = super(ConnectedAddressDescription, cls).description_from_socket(
            sck)

        pname = sck.getpeername()
        cad.remote_name, cad.remote_port = pname[:2]

        # TODO: need to do anything to support flowinfo and scopeid?

        return cad

    @property
    def remote_sockname_tuple(self):
        if self.sock_family == AF_INET:
            return (self.remote_name, self.remote_port)

        fi = self.flowinfo or 0
        scid = self.scopeid or 0
        return (self.remote_name, self.remote_port, fi, scid)

    def connect(self, data_callback, transport):
        """Attempt to connect this description.

        :returns: a SocketProxy object
        """
        if self.remote_name is None or self.remote_port is None:
            raise ValueError(
                'remote_name (%r) or remote_port %r are None' % (
                    self.remote_name, self.remote_port))

        self.deduce_missing_values()

        if any((self.sock_family is None, self.sock_type is None)):
            raise ValueError('sock_family (%r) or sock_type (%r) None' % (
                self.sock_family, self.sock_type))

        log.debug('Connect socket using %r', self)
        sck = socket.socket(self.sock_family, self.sock_type)
        sck.bind(self.sockname_tuple)
        log.debug(
            'Bind socket to %r, result %r', self.sockname_tuple,
            sck.getsockname())
        sck.connect(self.remote_sockname_tuple)
        log.debug(
            'Connect to %r, result (%r --> %r)', self.remote_sockname_tuple,
            sck.getsockname(), sck.getpeername())

        laddr = ConnectedAddressDescription.description_from_socket(sck)
        log.info('New connected socket: %s', laddr)

        csck = SocketProxy(
            local_address=laddr, socket=sck, data_callback=data_callback,
            is_connected=True, transport=transport)
        return csck

    def __str__(self):
        sp_str = super(ConnectedAddressDescription, self).__str__()

        return (
            '{sp_str} -> {self.remote_name}:'
            '{self.remote_port:d}'.format(**locals()))

    def deduce_missing_values(self):

        if self.sock_family is None:
            self.sock_family = IPAddressFamilyFromName(self.remote_name)

        super(ConnectedAddressDescription, self).deduce_missing_values()


class SocketProxy(
        DeepClass('_sck_', {
            'local_address': {dck.check: lambda x: isinstance(
                x, ListenDescription)},
            'socket': {
                dck.check: lambda x:
                    isinstance(x, socket_class) or hasattr(x, 'socket')},
            'data_callback': {dck.check: lambda x: isinstance(x, Callable)},
            'is_connected': {dck.gen: lambda: False},
            'transport': {dck.descriptor: WeakProperty},
            'connected_sockets': {dck.gen: WeakValueDictionary}
        }), Retainable):

    socket_proxies = []
    socket_info = {}

    def send(self, data):

        sck = self.socket

        def log_send(sname, pname, data):

            prot_log.info(
                "Sent %r -> %r\n>>>>>\n%s\n>>>>>", sname, pname,
                Transport.FormatBytesForLogging(data))

        if isinstance(sck, socket_class):
            log_send(sck.getsockname(), sck.getpeername(), data)
            return sck.send(data)

        # Socket shares a socket, so need to sendto.
        sck = sck.socket
        assert(sck.type == SOCK_DGRAM)
        paddr = self.local_address.remote_sockname_tuple
        log_send(sck.getsockname(), paddr, data)
        sck.sendto(data, paddr)

    def close(self):
        sck = self.socket
        if isinstance(sck, socket_class):
            try:
                sck.close()
            except socket_error as exc:
                log.warning('Exception closing socket: %s', exc)

        self.socket = None

    #
    # =================== CALLBACKS ===========================================
    #
    def socket_selected(self, sock):
        assert sock is self.socket, (sock, self.socket)
        if sock.type == SOCK_STREAM:
            return self._stream_socket_selected()
        return self._dgram_socket_selected()

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        log.info('DELETE %s instance', type(self).__name__)
        sck = self.socket
        if isinstance(sck, socket_class):

            if self.is_connected:
                try:
                    sck.shutdown(SHUT_RDWR)
                except:
                    log.debug('Exception shutting socket', exc_info=True)

            try:
                sck.close()
            except:
                log.debug('Exception closing socket', exc_info=True)

        getattr(super(SocketProxy, self), '__del__', lambda: None)()

    #
    # =================== INTERNAL METHODS ====================================
    #
    def _stream_socket_selected(self):
        self._readable_socket_selected()

    def _dgram_socket_selected(self):
        self._readable_socket_selected()

    def _readable_socket_selected(self):

        sname = self.socket.getsockname()
        log.debug('recvfrom %r local:%r', self.socket.type, sname)
        data, addr = self.socket.recvfrom(4096)
        if len(data) > 0:
            prot_log.info(
                " received %r -> %r\n<<<<<\n%s\n<<<<<", addr, sname,
                Transport.FormatBytesForLogging(data))

        if not self.is_connected:
            lad = self.local_address
            if is_null_address(lad.name):
                tsck = socket_class(lad.sock_family, lad.sock_type)
                tsck.connect(addr)
                lname = tsck.getsockname()
                tsck.close()
            else:
                lname = lad.sockname_tuple
            log.debug('Use local address %s', lname)

            csp = self.connected_sockets.get((lname[0], addr))
            if csp is None:
                log.debug('First receipt of data on this listen socket')
                # Therefore need to create a new 'connected' socket proxy that
                # uses our socket to send on.
                tp = self.transport
                if tp is not None:
                    desc = self.local_address
                    cad = ConnectedAddressDescription(
                        sock_family=desc.sock_family, sock_type=desc.sock_type,
                        name=lname[0], port=desc.port,
                        remote_name=addr[0], remote_port=addr[1])
                    csp = SocketProxy(
                        local_address=cad, socket=self, is_connected=True,
                        transport=tp)
                    log.info(
                        'New connected socket proxy using UDP listen socket: '
                        '%s' % (cad,))
                    tp.add_connected_socket_proxy(csp)
                    self.connected_sockets[(lname[0], addr)] = csp

        dc = self.data_callback
        if dc is None:
            raise NotImplementedError('No data callback specified.')

        log.debug('Passing data to callback %r', dc)
        dc(self, addr, data)


class Transport(Singleton):
    """Manages connection state and transport so You don't have to."""

    #
    # =================== CLASS INTERFACE =====================================
    #
    DefaultTransportType = SOCK_DGRAM
    DefaultPort = 0
    DefaultFamily = AF_INET

    @staticmethod
    def FormatBytesForLogging(mbytes):
        return '\\n\n'.join(
            [repr(astr(bs))[1:-1] for bs in mbytes.split(b'\n')]).rstrip('\n')

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    byteConsumer = DerivedProperty("_tp_byteConsumer")

    @property
    def connected_socket_count(self):
        return self._tp_count_vals_in_dict(self._tp_connected_sockets)

    @property
    def listen_socket_count(self):
        return self._tp_count_vals_in_dict(self._tp_listen_sockets)

    def _tp_count_vals_in_dict(self, rdict):
        count = 0
        for sock in self.yield_vals(rdict):
            count += 1
        return count

    def __init__(self):
        log.info('%s.__init__()', type(self).__name__)
        super(Transport, self).__init__()
        self._tp_byteConsumer = None
        self._tp_retryThread = RetryThread()

        # Series of dictionaries keyed by (in order):
        # - socket family (AF_INET etc.)
        # - socket type (SOCK_STREAM etc.)
        # - socket name
        # - socket port
        self._tp_listen_sockets = {}
        self._tp_connected_sockets = {}

    def listen_for_me(self, callback, sock_type=None, sock_family=None,
                      name=NameAll, port=0, port_filter=None, flowinfo=None,
                      scopeid=None, listen_description=None,
                      reuse_socket=True):

        if not isinstance(callback, Callable):
            raise TypeError(
                '\'callback\' parameter %r is not a Callable' % callback)

        if listen_description is None:
            sock_family = self.fix_sock_family(sock_family)
            if sock_family is None:
                sock_family = IPAddressFamilyFromName(name)

            sock_type = self.fix_sock_type(sock_type)

            provisional_laddr = ListenDescription(
                sock_family=sock_family, sock_type=sock_type, name=name,
                port=port, flowinfo=flowinfo, scopeid=scopeid,
                port_filter=port_filter)
        else:
            provisional_laddr = copy(listen_description)
        provisional_laddr.deduce_missing_values()

        tpl = self.convert_listen_description_into_find_tuple(
            provisional_laddr)
        path, lsck = self.find_cached_object(self._tp_listen_sockets, tpl)

        if lsck is not None:
            if reuse_socket:
                lsck.retain()
                return lsck.local_address

            raise SocketInUseError(
                'All sockets matcing Description %s are already in use.' % (
                    provisional_laddr))

        lsck = self.create_listen_socket(provisional_laddr, callback)
        return lsck.local_address

    # connect
    def get_send_from_address(
            self, sock_type=None, sock_family=None,
            name=SendFromAddressNameAny, port=0, flowinfo=None, scopeid=None,
            remote_name=None, remote_port=None, port_filter=None,
            data_callback=None,
            from_description=None, to_description=None):
        """Get a SocketProxy to send data on.

        :returns: SocketProxy instance.
        """
        if sock_family is None:
            sock_family = IPAddressFamilyFromName(remote_name)

        create_kwargs = {}
        for attr in (
                'sock_type', 'sock_family', 'name', 'port', 'flowinfo',
                'scopeid', 'port_filter'):
            create_kwargs[attr] = locals()[attr]

        for remote_attr, to_desc_attr in (
                ('remote_name', 'name'), ('remote_port', 'port')):
            create_kwargs[remote_attr] = locals()[remote_attr]

        create_kwargs['sock_type'] = self.fix_sock_type(
            create_kwargs['sock_type'])
        create_kwargs['sock_family'] = self.fix_sock_family(
            create_kwargs['sock_family'])
        cad = ConnectedAddressDescription(**create_kwargs)

        if (data_callback is not None and
                not isinstance(data_callback, Callable)):
            raise TypeError('data_callback must be a callback (was %r)' % (
                data_callback,))
        fsck = self.find_or_create_send_from_socket(cad, data_callback)

        return fsck

    def create_listen_socket(self, local_address, callback):
        lsck = local_address.listen(callback, self)
        self.add_listen_socket_proxy(lsck)
        return lsck

    def find_send_from_socket(self, cad):
        log.debug('Attempt to find send from address')
        tpl = self.convert_connected_address_description_into_find_tuple(cad)
        path, sck = self.find_cached_object(self._tp_connected_sockets, tpl)
        if sck is not None:
            sck.retain()
        return path, sck

    def find_or_create_send_from_socket(self, cad, data_callback=None):

        path, sck = self.find_send_from_socket(cad)
        if sck is not None:
            log.debug('Found existing send from socket')
            return sck

        sck = cad.connect(data_callback, self)

        self.add_connected_socket_proxy(sck, path=path)
        return sck

    def add_connected_socket_proxy(self, socket_proxy, *args, **kwargs):
        tpl = self.convert_connected_address_description_into_find_tuple(
            socket_proxy.local_address)
        self._add_socket_proxy(
            socket_proxy, self._tp_connected_sockets, tpl, *args, **kwargs)
        log.detail('connected sockets now: %r', self._tp_connected_sockets)

    def add_listen_socket_proxy(self, listen_socket_proxy, *args, **kwargs):
        tpl = self.convert_listen_description_into_find_tuple(
            listen_socket_proxy.local_address)
        self._add_socket_proxy(
            listen_socket_proxy, self._tp_listen_sockets, tpl, *args, **kwargs)

    def find_cached_object(self, cache_dict, find_tuple):

        log.debug('Find tuple: %r', [_item[0] for _item in find_tuple])
        full_path_len = len(find_tuple)
        path = [
            (key, obj) for key, obj in self.yield_dict_path(
                cache_dict, find_tuple)]

        log.debug(
            'Path is %d long, full find tuple is %d long', len(path),
            full_path_len)

        assert not (len(path) == 7 and full_path_len == 8), path[-1]

        assert len(path) <= full_path_len
        if len(path) == full_path_len:
            lsck = path[-1][1]
            log.debug('Found object %r', lsck)
            return path, lsck

        return path, None

    def release_listen_address(self, description=None, **kwargs):
        log.debug('Release %r', description)
        if (description is not None and not isinstance(
                description, ListenDescription)) or (
                description is None and not kwargs):

            raise TypeError(
                'Cannot release something which is not a ListenDescription: '
                '%r' % (description,))

        if description is None:
            description = ListenDescription(**kwargs)
            description.deduce_missing_values()

        if isinstance(description, ConnectedAddressDescription):
            log.debug('Release connected address')
            root_dict = self._tp_connected_sockets
            ftup = self.convert_connected_address_description_into_find_tuple(
                description)
        else:
            log.debug('Release listen address')
            root_dict = self._tp_listen_sockets
            ftup = self.convert_listen_description_into_find_tuple(description)

        path, lsck = self.find_cached_object(root_dict, ftup)
        if lsck is None:
            raise KeyError(
                '%r was not a known ListenDescription.' % (description))

        lsck.release()
        if not lsck.is_retained:
            log.debug('Listen address no longer retained')
            ldict = path[-2][1]
            key = path[-1][0]

            if isinstance(lsck.socket, socket_class):
                self._tp_retryThread.rmInputFD(lsck.socket)
            try:
                lsck.close()
            except Exception as exc:
                log.warning(
                    'Exception closing socket for %s: %s', self, exc)
            del ldict[key]

    def resolve_host(self, host, port=None, family=None):
        """Resolve a host.
        :param bytes host: A host in `bytes` form that we want to resolve.
        May be a domain name or an IP address.
        :param integer,None port: A port we want to connect to on the host.
        """
        if port is None:
            port = self.DefaultPort
        if not isinstance(port, Integral):
            raise TypeError('Port is not an Integer: %r' % port)
        if not IsValidPortNum(port):
            raise ValueError('Invalid port number: %r' % port)
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
        except socket.gaierror:
            pass

        raise(UnresolvableAddress(address=host, port=port))

    def close_all(self):
        """Last ditch attempt to avoid leaving sockets lying around."""
        log.info('Closing all sockets.')
        for sock_dicts in (
                self._tp_listen_sockets, self._tp_connected_sockets):
            socks = [path[-1][1] for path in self.yield_vals(dict(sock_dicts))]
            for sock in socks:
                assert sock is not None
                self.release_listen_address(sock.local_address)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):

        log.info('DELETE %s instance', self.__class__.__name__)
        self._tp_retryThread.cancel()

        self.close_all()

        sp = super(Transport, self)
        getattr(sp, '__del__', lambda: None)()

    #
    # =================== INTERNAL METHODS ====================================
    #
    def _add_socket_proxy(self, socket_proxy, root_dict, find_tuple, path=()):
        if isinstance(socket_proxy.socket, socket_class):
            self._tp_retryThread.addInputFD(
                socket_proxy.socket,
                WeakMethod(socket_proxy, 'socket_selected'))
        socket_proxy.retain()
        keys = [obj[0] for obj in find_tuple[len(path):]]
        log.detail('_add_socket_proxy keys: %r', keys)

        sub_root = path[-1][1] if len(path) > 0 else root_dict
        self.insert_cached_object(
            sub_root, keys, socket_proxy)

    @staticmethod
    def insert_cached_object(root, path, obj):
        next_dict = root
        for key in path[:-1]:
            new_dict = next_dict.get(key, {})
            next_dict[key] = new_dict
            next_dict = new_dict
        next_dict[path[-1]] = obj
        return

    @staticmethod
    def convert_listen_description_into_find_tuple(listen_address):

        pfilter = listen_address.port_filter

        def first_entry_if_key_else_new(cond):
            def find_first_entry(pdict, key):
                if cond(key):
                    for key, val in iteritems(pdict):
                        return key, val
                return None, None

            return find_first_entry

        def find_suitable_port(pdict, port):
            if port:
                return None, None

            for port, next_dict in iteritems(pdict):
                if pfilter is None or pfilter(port):
                    return port, next_dict

            return None, None

        def find_suitable_name(pdict, name):
            log.debug('Find name for %r in keys %r', name, pdict.keys())
            if name is NameAll:
                for _all in (
                        AllAddressesFromFamily(AF_INET),
                        AllAddressesFromFamily(AF_INET6)):
                    if _all in pdict:
                        return _all, pdict[_all]

                return None, None

            if name is SendFromAddressNameAny:
                for name, name_dict in iteritems(pdict):
                    return name, name_dict

            return None, None

        def find_suitable_flowinfo_or_scopeid(pdict, val):
            log.debug(
                'Find flowinfo or scopeid for %r in keys %r', val,
                pdict.keys())
            if val is not None:
                return None, None

            for name, name_dict in iteritems(pdict):
                return name, name_dict

            return None, None

        rtup = (
            (listen_address.sock_family, first_entry_if_key_else_new(
                lambda key: key is None)),
            (listen_address.sock_type, first_entry_if_key_else_new(
                lambda key: key is None)),
            (listen_address.name, find_suitable_name),
            (listen_address.port, find_suitable_port),
            (listen_address.flowinfo, find_suitable_flowinfo_or_scopeid),
            (listen_address.scopeid, find_suitable_flowinfo_or_scopeid))

        sock_family = listen_address.sock_family or DEFAULT_SOCK_FAMILY
        if sock_family == AF_INET:
            return rtup[:-2]
        return rtup

    @staticmethod
    def convert_connected_address_description_into_find_tuple(cad):

        ladtuple = Transport.convert_listen_description_into_find_tuple(cad)

        # The remote address is more significant than the local one. So we
        # allow a caller to request a connection to a particular address, but
        # leave the local address undefined.

        return (
            ladtuple[:2] + ((cad.remote_name, None), (cad.remote_port, None)) +
            ladtuple[2:])

    _yield_sentinel = type('YieldDictPathSentinel', (), {})()

    @classmethod
    def yield_dict_path(cls, root_dict, lookups):
        next_dict = root_dict
        sentinel = cls._yield_sentinel
        for key, finder in lookups:
            log.debug('Find next key %r from keys %r', key, next_dict.keys())
            obj = next_dict.get(key, sentinel)
            if obj is sentinel:
                if not isinstance(finder, Callable):
                    return

                key, obj = finder(next_dict, key)
                if obj is None:
                    return
                next_dict[key] = obj
            yield key, obj
            if not isinstance(obj, dict):
                # We're done.
                return
            next_dict = obj

    @classmethod
    def yield_vals(cls, root_dict, path_so_far=None):
        """Yields all vals in the dictionary passed in with the
        """
        if path_so_far is None:
            path_so_far = []

        for key, val in iteritems(root_dict):
            if val is None:
                continue

            path_so_far.append((key, val))
            if isinstance(val, dict):
                for path in cls.yield_vals(val, path_so_far):
                    yield path
                continue
            else:
                yield tuple(path_so_far)
            path_so_far.pop()

    def fix_sock_family(self, sock_family):
        if sock_family not in (None,) + tuple(SOCK_FAMILIES):
            raise TypeError(
                'Invalid socket family: %s' % SockFamilyName(sock_family))

        return sock_family

    def fix_sock_type(self, sock_type):
        if sock_type is None:
            sock_type = self.DefaultTransportType

        if sock_type not in SOCK_TYPES:
            raise ValueError(
                "Socket type must be one of %r" % (SOCK_TYPES_NAMES,))

        return sock_type
