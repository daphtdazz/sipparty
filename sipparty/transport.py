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
from collections import Callable
from six import (binary_type as bytes, iteritems, itervalues)
import socket  # TODO: should remove and rely on from socket import ... below.
import logging
from socket import (
    socket as socket_class, SOCK_STREAM, SOCK_DGRAM, AF_INET, AF_INET6,
    gethostname)
from numbers import Integral
import re
from .deepclass import (dck, DeepClass)
from .fsm import (RetryThread)
from .util import (
    abytes, AsciiBytesEnum, astr, bglobals_g, DelegateProperty,
    DerivedProperty, Enum, Singleton,
    TupleRepresentable, TwoCompatibleThree, WeakMethod)


def bglobals():
    return bglobals_g(globals())

SOCK_TYPES = Enum((SOCK_STREAM, SOCK_DGRAM))
SOCK_TYPES_NAMES = AsciiBytesEnum((b"SOCK_STREAM", b"SOCK_DGRAM"))
SOCK_TYPE_IP_NAMES = AsciiBytesEnum((b"TCP", b"UDP"))
SOCK_FAMILIES = Enum((AF_INET, AF_INET6))
SOCK_FAMILY_NAMES = AsciiBytesEnum((b"IPv4", b"IPv6"))
log = logging.getLogger(__name__)
prot_log = logging.getLogger("messages")

# RFC 2373 IPv6 address format definitions.
digitrange = b"0-9"
DIGIT = b"[%(digitrange)s]" % bglobals()
hexrange = b"%(digitrange)sa-fA-F" % bglobals()
HEXDIG = b"[%(hexrange)s]" % bglobals()
hex4 = b"%(HEXDIG)s{1,4}" % bglobals()
# Surely IPv6 address length is limited?
hexseq = b"%(hex4)s(?::%(hex4)s)*" % bglobals()
hexpart = (
    b"(?:%(hexseq)s|%(hexseq)s::(?:%(hexseq)s)?|::(?:%(hexseq)s)?)" %
    bglobals())
IPv4address = b"%(DIGIT)s{1,3}(?:[.]%(DIGIT)s{1,3}){3}" % bglobals()
IPv6address = b"%(hexpart)s(?::%(IPv4address)s)?" % bglobals()
IPaddress = b"(?:%(IPv4address)s|%(IPv6address)s)" % bglobals()
port = b"%(DIGIT)s+" % bglobals()

# Some pre-compiled regular expression versions.
IPv4address_re = re.compile(IPv4address + b'$')
IPv6address_re = re.compile(IPv6address + b'$')
IPaddress_re = re.compile(IPaddress + b'$')


def default_hostname():
    return gethostname()


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
    if socktype == SOCK_STREAM:
        return SOCK_TYPE_IP_NAMES.TCP
    if socktype == SOCK_DGRAM:
        return SOCK_TYPE_IP_NAMES.UDP

    assert socktype in SOCK_TYPES


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
    assert socktype in (0, socket.SOCK_STREAM, socket.SOCK_DGRAM)

    address = list(address)
    if address[0] is None:
        address[0] = default_hostname()

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
            log.debug("Using just passed port %d", address[1])
            yield address[1]
            return

        # Guess a port from the unregistered range.
        for ii in range(49152, 0xffff):
            if port_filter is None or port_filter(ii):
                yield ii

    socketError = None
    for port in port_generator():
        try:
            # TODO: catch specific errors (e.g. address in use) to bail
            # immediately rather than inefficiently try all ports.
            log.detail("Try port %d", port)
            ssocket.bind((address[0], port))
            socketError = None
            break
        except socket.error as _se:
            log.debug("Socket error on (%r, %d)", address[0], port)
            socketError = _se
        except socket.gaierror as _se:
            log.debug("GAI error on (%r, %d)", address[0], port)
            socketError = _se
            break

    if socketError is not None:
        raise BadNetwork(
            "Couldn't bind to address %s" % address[0],
            socketError)

    log.debug("Socket bound to %r type %r", ssocket.getsockname(), _family)
    return ssocket


def ValidPortNum(port):
    return 0 < port <= 0xffff


class ListenAddress(
        DeepClass('_laddr_', {
            'port': {dck.check: lambda x: x == 0 or ValidPortNum(x)},
            'sock_family': {dck.check: lambda x: x in SOCK_FAMILIES},
            'sock_type': {dck.check: lambda x: x in SOCK_TYPES},
            'name': {},
            'flowinfo': {dck.check: lambda x: x == 0},
            'scopeid': {dck.check: lambda x: x == 0},
            'port_filter': {dck.check: lambda x: isinstance(x, Callable)}}),
        TupleRepresentable):

    @classmethod
    def address_from_socket(cls, sck):
        sname = sck.getsockname()

        addr = cls(
            name=sname[0], sock_family=sck.family, sock_type=sck.type,
            port=sname[1], flowinfo=None if len(sname) == 2 else sname[2],
            scopeid=None if len(sname) == 2 else sname[3])
        return addr

    def __init__(
            self, name, sock_family, sock_type, flowinfo=None,
            scopeid=None, **kwargs):

        if sock_family == AF_INET6:
            for ip6_attr in ('flowinfo', 'scopeid'):
                if locals()[ip6_attr] is None:
                    raise TypeError(
                        'Must specify %r for and IPv6 address.' % ip6_attr)

        for attr in (
                'name', 'sock_family', 'sock_type', 'flowinfo',
                'scopeid'):
            kwargs[attr] = locals()[attr]

        super(ListenAddress, self).__init__(**kwargs)

    @property
    def sockname_tuple(self):
        if self.name == Transport.SendFromAddressNameAny:
            name = '0.0.0.0' if self.sock_family == AF_INET else '::'
        else:
            name = self.name
        if self.sock_family == AF_INET:
            return (name, self.port)
        return (name, self.port, self.flowinfo, self.scopeid)

    def tupleRepr(self):
        return (
            self.__class__, self.sock_family, self.sock_type, self.port,
            self.name)

    def listen(self):
        """Return a _ListenSocket using the ListenAddress's parameters, or
        raise an exception if not possible.
        """
        lsck = GetBoundSocket(
            self.sock_family, self.sock_type, self.sockname_tuple,
            self.port_filter)

        laddr = self.address_from_socket(lsck)

        return _ListenSocket(laddr, lsck)


class ConnectedAddressDescription(
        DeepClass('_cad_', {
            'remote_name': {},
            'remote_port': {dck.check: ValidPortNum},
        }, recurse_repr=True),
        ListenAddress):

    @classmethod
    def address_from_socket(cls, sck):
        cad = super(ConnectedAddressDescription, cls).address_from_socket(sck)

        cad.remote_name, cad.remote_port = sck.getpeername()
        return cad

    @property
    def remote_sockname_tuple(self):
        if self.sock_family == AF_INET:
            return (self.remote_name, self.remote_port)
        return (
            self.remote_name, self.remote_port, self.flowinfo, self.scopeid)

    def connect(self):
        """Attempt to connect this description.
        :returns: _ConnectedSocket
        """

        sck = socket.socket(self.sock_family, self.sock_type)
        sck.bind(self.sockname_tuple)
        sck.connect(self.remote_sockname_tuple)

        csck = _ConnectedSocket(
            local_address = ConnectedAddressDescription.address_from_socket(
                sck),
            socket=sck)

        return csck


class Retainable(object):

    def __init__(self):
        super(Retainable, self).__init__()
        self.__retain_count = 0

    @property
    def is_retained(self):
        return self.__retain_count != 0

    def retain(self):
        self.__retain_count += 1
        log.debug('retain count now %d', self.__retain_count)

    def release(self):
        self.__retain_count -= 1
        log.debug('retain count now %d', self.__retain_count)


class _Socket(
        DeepClass('_sck_', {
            'local_address': {dck.check: lambda x: isinstance(
                x, ListenAddress)},
            'socket': {dck.check: lambda x: isinstance(x, socket_class)}
        }), Retainable):

    send = DelegateProperty('socket', 'send')

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        sck = self.socket
        if sck is not None:
            sck.shutdown()

        dtr = getattr(super(self, _ListenSocket), '__del__', None)
        if dtr is not None:
            dtr()

class _ListenSocket(_Socket):

    @property
    def listen_address(self):
        return self.local_address

    def __init__(self, listen_address, socket, **kwargs):
        for attr in ('socket',):
            kwargs[attr] = locals()[attr]
        kwargs['local_address'] = listen_address

        super(_ListenSocket, self).__init__(**kwargs)


class _ConnectedSocket(_Socket):
    pass


class Transport(Singleton):
    """Manages connection state and transport so You don't have to."""
    #
    # =================== CLASS INTERFACE =====================================
    #
    DefaultTransportType = SOCK_DGRAM
    DefaultPort = 0
    DefaultFamily = AF_INET

    NameAll = type(
        'ListenNameAllAddresses', (), {
            '__repr__': lambda self: __name__ + '.Transport.NameAll',
            '__doc__': (
                'Use this singleton object in your call to listen_for_me to '
                'indicate that you wish to listen on all addresses.')})()
    NameLANHostname = type(
        'ListenNameLANHostname', (), {
            '__repr__': lambda self: __name__ + '.Transport.NameLANHostname',
            '__doc__': (
                'Use this singleton object in your call to listen_for_me to '
                'indicate that you wish to listen on an address you have '
                'exposed on the Local Area Network.')})()

    SendFromAddressNameAny = type(
        'SendFromAddressNameAny', (), {
            '__repr__': lambda self: (
                __name__ + '.Transport.SendFromAddressNameAny'),
            '__doc__': (
                'Use this singleton object in your call to '
                'get_send_from_address to '
                'indicate that you wish to send from any routable '
                'local address.')})()

    @classmethod
    def FormatBytesForLogging(cls, mbytes):
        return '\\n\n'.join(
            [repr(astr(bs))[1:-1] for bs in mbytes.split(b'\n')]).rstrip('\n')

    #
    # =================== INSTANCE INTERFACE ==================================
    #
    byteConsumer = DerivedProperty("_tp_byteConsumer")

    def __init__(self):
        if self.singletonInited:
            return
        super(Transport, self).__init__()
        self._tp_byteConsumer = None
        self._tp_retryThread = RetryThread()
        self._tp_retryThread.start()

        # Series of dictionaries keyed by (in order):
        # - socket family (AF_INET etc.)
        # - socket type (SOCK_STREAM etc.)
        # - socket name
        # - socket port
        self._tp_listen_sockets = {}
        self._tp_connected_sockets = {}

        # Keyed by (lAddr, rAddr) independent of type.
        self._tp_connBuffers = {}
        # Keyed by local address tuple.
        self._tp_dGramSockets = {}

    def listen_for_me(self, callback, sock_type=None, sock_family=None,
                      name=NameAll, port=0, port_filter=None, flowinfo=0,
                      scopeid=0):

        if flowinfo != 0 or scopeid != 0:
            raise NotImplementedError(
                'flowinfo and scopeid with values other than 0 can\'t be used '
                'yet.')

        if not isinstance(callback, Callable):
            raise TypeError(
                '\'callback\' parameter %r is not a Callable' % callback)

        sock_family = self.fix_sock_family(sock_family)

        if name is self.NameAll:
            name = '0.0.0.0' if sock_family == AF_INET else '::'
        elif name is self.NameLANHostname:
            name = default_hostname()

        sock_type = self.fixSockType(sock_type)

        provisional_laddr = ListenAddress(
            sock_family=sock_family, sock_type=sock_type, name=name,
            port=port, flowinfo=flowinfo, scopeid=scopeid,
            port_filter=port_filter)

        lsck = self.find_or_create_listen_socket(provisional_laddr)

        return lsck.local_address

    def get_send_from_address(
            self, sock_type=None, sock_family=None,
            name=SendFromAddressNameAny, port=0, flowinfo=0, scopeid=0,
            remote_name=None, remote_port=None, port_filter=None):

        sock_type = self.fixSockType(sock_type)
        sock_family = self.fix_sock_family(sock_family)

        cad = ConnectedAddressDescription(
            sock_type=sock_type, sock_family=sock_family, name=name, port=port,
            port_filter=port_filter, flowinfo=flowinfo, scopeid=scopeid,
            remote_name=remote_name, remote_port=remote_port)

        fsck = self.find_or_create_send_from_socket(cad)

        return fsck.local_address

    def send(self, data, cad):
        _, csck = self.find_send_from_socket(cad)
        if csck is None:
            raise KeyError('No socket for address %r', cad)

        csck.send(data)

    def find_or_create_listen_socket(self, local_address):

        log.debug('Find local address %r', local_address)
        tpl = self.convert_listen_address_into_find_tuple(local_address)
        path, lsck = self.find_cached_object(self._tp_listen_sockets, tpl)

        if lsck is not None:
            log.debug('Found socket')
            lsck.retain()
            return lsck

        _sck = local_address.listen()
        _sck.retain()

        sub_root = path[-1][1] if len(path) > 0 else self._tp_listen_sockets

        tpl = self.convert_listen_address_into_find_tuple(_sck.local_address)
        self.insert_cached_object(
            sub_root, [obj[0] for obj in tpl[len(path):]], _sck)

        return _sck

    def find_send_from_socket(self, cad):
        log.debug('Attempt to find send from address')
        tpl = self.convert_connected_address_description_into_find_tuple(cad)
        path, sck = self.find_cached_object(self._tp_connected_sockets, tpl)
        if sck is not None:
            sck.retain()
        return path, sck

    def find_or_create_send_from_socket(self, cad):

        path, sck = self.find_send_from_socket(cad)
        if sck is not None:
            log.debug('Found existing send from socket')
            return sck

        sck = cad.connect()
        sck.retain()

        sub_root = path[-1][1] if len(path) > 0 else self._tp_connected_sockets

        tpl = self.convert_connected_address_description_into_find_tuple(
            sck.local_address)
        self.insert_cached_object(
            sub_root, [obj[0] for obj in tpl[len(path):]], sck)

        return sck

    def find_cached_object(self, cache_dict, find_tuple):

        log.debug('Cache dict: %r', cache_dict)
        log.debug('Find tuple: %r', find_tuple)
        full_path_len = len(find_tuple)
        path = [
            (key, obj) for key, obj in self.yield_dict_path(
                cache_dict,
                find_tuple)]

        log.debug(
            'Path is %d long, full find tuple is %d long', len(path),
            full_path_len)

        assert len(path) <= full_path_len
        if len(path) == full_path_len:
            lsck = path[-1][1]
            log.debug('Found object %r', lsck)
            return path, lsck
        return path, None

    @staticmethod
    def insert_cached_object(root, path, obj):

        next_dict = root
        for key in path[:-1]:
            new_dict = {}
            next_dict[key] = new_dict
            next_dict = new_dict
        next_dict[path[-1]] = obj
        return

        last_obj = path[-1][1]
        if len(path) <= self._listen_path_name_index:
            nd = {}
            last_obj[_sck.local_address.name] = nd
            last_obj = nd

        assert 0, (tpl, path)
        if len(path) <= self._listen_path_port_index:
            nd = {} if _sck.local_address.sock_family == AF_INET6 else _sck
            last_obj[_sck.local_address.port] = nd
            last_obj = nd

        if _sck.local_address.sock_family == AF_INET:
            return _sck

        assert 0

        return lsck

    _yield_sentinel = type('YieldDictPathSentinel', (), {})()
    @classmethod
    def yield_dict_path(cls, root_dict, lookups):
        next_dict = root_dict
        sentinel = cls._yield_sentinel
        for key, finder in lookups:
            obj = next_dict.get(key, sentinel)
            if obj is sentinel:
                if not isinstance(finder, Callable):
                    return

                key, obj = finder(next_dict, key)
                if obj is None:
                    return
                next_dict[key] = obj
            yield key, obj
            next_dict = obj

    _listen_path_name_index = 2
    _listen_path_port_index = 3
    @staticmethod
    def convert_listen_address_into_find_tuple(listen_address):

        pfilter = listen_address.port_filter
        def find_suitable_port(pdict, port):
            if port != 0:
                return None, None

            for port, next_dict in iteritems(pdict):
                if pfilter is None or pfilter(port):
                    return port, next_dict

            return None, None

        def find_suitable_name(pdict, name):
            if name != Transport.SendFromAddressNameAny:
                return None, None

            for name, name_dict in iteritems(pdict):
                return name, name_dict

            return None, None

        rtup = (
            (listen_address.sock_family, lambda _dict, key: (key, {})),
            (listen_address.sock_type, lambda _dict, key: (key, {})),
            (listen_address.name, find_suitable_name),
            (listen_address.port, find_suitable_port),
            (listen_address.flowinfo, lambda _dict, key: (key, {})),
            (listen_address.scopeid, None))
        if listen_address.sock_family == AF_INET:
            return rtup[:-2]
        return rtup

    @staticmethod
    def convert_connected_address_description_into_find_tuple(cad):

        ladtuple = Transport.convert_listen_address_into_find_tuple(cad)

        # The remote address is more significant than the local one. So we
        # allow a caller to request a connection to a particular address, but
        # leave the local address undefined.

        return (
            ladtuple[:2] + ((cad.remote_name, None), (cad.remote_port, None)) +
            ladtuple[2:])

    def release_listen_address(self, listen_address):
        log.debug('Release %r', listen_address)
        if not isinstance(listen_address, ListenAddress):
            raise TypeError(
                'Cannot release something which is not a ListenAddress: %r' % (
                    listen_address))

        path, lsck = self.find_cached_object(
            self._tp_listen_sockets,
            self.convert_listen_address_into_find_tuple(listen_address))
        if lsck is None:
            raise KeyError(
                '%r was not a known ListenAddress.' % (listen_address))

        lsck.release()
        if not lsck.is_retained:
            log.debug('Listen address no longer retained')
            ldict = path[-2][1]
            key = path[-1][0]
            del ldict[key]

    def resolveHost(self, host, port=None, family=None):
        """Resolve a host.
        :param bytes host: A host in `bytes` form that we want to resolve.
        May be a domain name or an IP address.
        :param integer,None port: A port we want to connect to on the host.
        """
        if port is None:
            port = self.DefaultPort
        if not isinstance(port, Integral):
            raise TypeError('Port is not an Integer: %r' % port)
        if 0 > port > 0xffff:
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

    def sendMessage(self, msg, toAddr, fromAddr=None, sockType=None):
        sockType = self.fixSockType(sockType)
        if sockType == SOCK_DGRAM:
            return self._sendDgramMessage(msg, toAddr, fromAddr)

        return self.sendStreamMessage(msg, toAddr, fromAddr)

    def _sendDgramMessage(self, msg, toAddr, fromAddr):
        assert isinstance(msg, bytes)

        if fromAddr is not None:
            try:
                return self._sendDgramMessageFrom(msg, toAddr, fromAddr)
            except BadNetwork:
                log.error(
                    "Bad network, currently have sockets: %r",
                    self._tp_dGramSockets)
                raise

        # TODO: cache sockets used for particular toAddresses so we can re-use
        # them faster.

        # Try and find a socket we can route through.
        log.debug("Send msg to %r from anywhere", toAddr)
        for sck in itervalues(self._tp_dGramSockets):
            sname = sck.getsockname()
            try:
                if len(toAddr) != len(sname):
                    log.debug("Different socket family type skipped.")
                    continue
                sck.sendto(msg, toAddr)
                prot_log.info(
                    "Sent %r -> %r\n>>>>>\n%s\n>>>>>", sname,
                    toAddr, self.FormatBytesForLogging(msg))
                return
            except socket.error as exc:
                log.debug(
                    "Could not sendto %r from %r: %s", toAddr,
                    sname, exc)
        else:
            raise exc

    def _sendDgramMessageFrom(self, msg, toAddr, fromAddr):
        """:param msg: The message (a bytes-able) to send.
        :param toAddr: The place to send to. This should be *post* address
        resolution, so this must be either a 2 (IPv4) or a 4 (IPv6) tuple.
        """
        log.debug("Send %r -> %r", fromAddr, toAddr)

        assert isinstance(toAddr, tuple)
        assert len(toAddr) in (2, 4)

        family = AF_INET if len(toAddr) == 2 else AF_INET6

        fromName, fromPort = fromAddr[:2]

        if fromName is not None and IPv6address_re.match(
                abytes(fromName)):
            if len(fromAddr) == 2:
                fromAddr = (fromAddr[0], fromAddr[1], 0, 0)
            else:
                assert len(fromAddr) == 4

        if fromAddr not in self._tp_dGramSockets:
            sck = GetBoundSocket(family, SOCK_DGRAM, fromAddr)
            self.addDgramSocket(sck)
        else:
            sck = self._tp_dGramSockets[fromAddr]
        sck.sendto(msg, toAddr)

    def addDgramSocket(self, sck):
        self._tp_dGramSockets[sck.getsockname()] = sck
        log.debug("%r Dgram sockets now: %r", self, self._tp_dGramSockets)

    #
    # =================== MAGIC METHODS =======================================
    #
    def __new__(cls, *args, **kwargs):
        if "singleton" not in kwargs:
            kwargs["singleton"] = "Transport"
        return super(Transport, cls).__new__(cls, *args, **kwargs)

    def __del__(self):
        self._tp_retryThread.cancel()
        sp = super(Transport, self)
        if hasattr(sp, "__del__"):
            sp.__del__()

    #
    # =================== INTERNAL METHODS ====================================
    #
    def fix_sock_family(self, sock_family):
        if sock_family is None:
            raise NotImplementedError(
                'Currently you must specify an IP family.')
        if sock_family not in SOCK_FAMILIES:
            raise TypeError(
                'Invalid socket family: %s' % SockFamilyName(sock_family))

        return sock_family

    def fixSockType(self, sock_type):
        if sock_type is None:
            sock_type = self.DefaultTransportType

        if sock_type not in SOCK_TYPES:
            raise ValueError(
                "Socket type must be one of %r" % (SOCK_TYPES_NAMES,))

        return sock_type

    def listenDgram(self, lAddrName, port, port_filter):
        sock = GetBoundSocket(None, SOCK_DGRAM, (lAddrName, port), port_filter)
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
            len_used = self.processReceivedData(lAddr, rAddr, buf)
            if len_used == 0:
                log.debug("Consumer stopped consuming")
                break
            log.debug("Consumer consumed another %d bytes", len_used)
            del buf[:len_used]

    def processReceivedData(self, lAddr, rAddr, data):

        bc = self.byteConsumer
        if bc is None:
            log.debug("No consumer; dumping data: %r.", data)
            return len(data)

        data_consumed = bc(lAddr, rAddr, bytes(data))
        if not isinstance(data_consumed, Integral):
            raise ValueError(
                "byteConsumer returned %r: must return an integer." % (
                    data_consumed,))
        return data_consumed
