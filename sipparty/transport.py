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
import logging
from numbers import Integral
import re
from six import (binary_type as bytes, iteritems, itervalues)
import socket  # TODO: should remove and rely on from socket import ... below.
from socket import (
    AF_INET, AF_INET6, getaddrinfo, gethostname, SHUT_RDWR,
    socket as socket_class,
    SOCK_STREAM, SOCK_DGRAM)
from weakref import ref
from .deepclass import (dck, DeepClass)
from .fsm import (RetryThread)
from .util import (
    abytes, AsciiBytesEnum, astr, bglobals_g, DelegateProperty,
    DerivedProperty, Enum, Singleton, Retainable,
    TupleRepresentable, TwoCompatibleThree, WeakMethod, WeakProperty)


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
IPaddress = b"(?:(%(IPv4address)s)|(%(IPv6address)s))" % bglobals()
port = b"%(DIGIT)s+" % bglobals()

# Some pre-compiled regular expression versions.
IPv4address_re = re.compile(IPv4address + b'$')
IPv6address_re = re.compile(IPv6address + b'$')
IPaddress_re = re.compile(IPaddress + b'$')


def IPAddressFamilyFromName(name):
    """Returns the family of the IP address passed in in name, or None if it
    could not be determined.
    :param name: The IP address or domain name to try and work out the family
    of.
    :returns: None, AF_INET or AF_INET6.
    """
    mo = IPaddress_re.match(name)

    if mo is None:
        return None

    if mo.group(1) is not None:
        return AF_INET

    assert mo.group(2) is not None
    return AF_INET6


def default_hostname():
    return gethostname()


def ValidPortNum(port):
    return 0 < port <= 0xffff


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


class SocketInUseError(TransportException):
    pass


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
    assert socktype in (0, SOCK_STREAM, SOCK_DGRAM)

    address = list(address)
    if address[0] is None:
        address[0] = default_hostname()

    # family e.g. AF_INET / AF_INET6
    # socktype e.g. SOCK_STREAM
    # Just grab the first addr info if we haven't
    log.debug("GetBoundSocket addr:%r port:%r family:%r socktype:%r...",
              address[0], address[1], family, SockTypeName(socktype))

    addrinfos = getaddrinfo(address[0], address[1], family, socktype)
    log.debug("Got addresses.")
    log.detail("  %r", addrinfos)

    if len(addrinfos) == 0:
        raise BadNetwork("Could not find an address to bind to %r." % address)

    _family, _socktype, _proto, _canonname, address = addrinfos[0]

    ssocket = socket_class(_family, socktype)

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
            ssocket.bind((address[0], port))
            log.debug(
                'Bind socket to %r, result %r', (address[0], port),
                ssocket.getsockname())
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


class ListenDescription(
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
    def description_from_socket(cls, sck):
        sname = sck.getsockname()

        addr = cls(
            name=sname[0], sock_family=sck.family, sock_type=sck.type,
            port=sname[1], flowinfo=None if len(sname) == 2 else sname[2],
            scopeid=None if len(sname) == 2 else sname[3])
        return addr

    def __init__(
            self, name, sock_family, sock_type, flowinfo=None,
            scopeid=None, **kwargs):

        for attr in (
                'name', 'sock_family', 'sock_type', 'flowinfo',
                'scopeid'):
            kwargs[attr] = locals()[attr]

        super(ListenDescription, self).__init__(**kwargs)

        if self.sock_family == AF_INET6:
            for ip6_attr in ('flowinfo', 'scopeid'):
                if getattr(self, ip6_attr) is None:
                    raise TypeError(
                        'Must specify %r for and IPv6 address.' % ip6_attr)

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

    def listen(self, data_callback, transport):
        """Return a SocketProxy using the ListenDescription's parameters, or
        raise an exception if not possible.
        """
        lsck = GetBoundSocket(
            self.sock_family, self.sock_type, self.sockname_tuple,
            self.port_filter)

        laddr = self.description_from_socket(lsck)

        return SocketProxy(
            local_address=laddr, socket=lsck, data_callback=data_callback,
            transport=transport)


class ConnectedAddressDescription(
        DeepClass('_cad_', {
            'remote_name': {},
            'remote_port': {dck.check: ValidPortNum},
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
        return (
            self.remote_name, self.remote_port, self.flowinfo, self.scopeid)

    def connect(self, data_callback, transport):
        """Attempt to connect this description.
        :returns: a SocketProxy object
        """

        log.debug('Connect socket using %r', self)
        sck = socket.socket(self.sock_family, self.sock_type)
        sck.bind(self.sockname_tuple)
        log.debug(
            'Bind socket to %r, result %r', self.sockname_tuple,
            sck.getsockname())
        sck.connect(self.remote_sockname_tuple)

        csck = SocketProxy(
            local_address=ConnectedAddressDescription.description_from_socket(
                sck),
            socket=sck,
            data_callback=data_callback, is_connected=True,
            transport=transport)
        return csck


class SocketProxy(
        DeepClass('_sck_', {
            'local_address': {dck.check: lambda x: isinstance(
                x, ListenDescription)},
            'socket': {dck.check: lambda x:
                isinstance(x, socket_class) or hasattr(x, 'socket')},
            # dc(socket_description, data)
            'data_callback': {dck.check: lambda x: isinstance(x, Callable)},
            'is_connected': {dck.gen: lambda: False},
            'transport': {dck.descriptor: WeakProperty}
        }), Retainable):

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

    #
    # =================== CALLBACKS ===========================================
    #
    def socket_selected(self, sock):
        assert sock is self.socket
        if sock.type == SOCK_STREAM:
            return self._stream_socket_selected()
        return self._dgram_socket_selected()

    #
    # =================== MAGIC METHODS =======================================
    #
    def __del__(self):
        sck = self.socket
        if isinstance(sck, socket_class):

            if self.is_connected:
                try:
                    sck.shutdown(SHUT_RDWR)
                except:
                    log.debug('Exception shutting socket.', exc_info=True)
            sck.close()

        assert isinstance(SocketProxy, type)
        dtr = getattr(super(SocketProxy, self), '__del__', None)
        if dtr is not None:
            dtr()

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
            tp = self.transport
            if tp is not None:
                desc = self.local_address
                cad = ConnectedAddressDescription(
                    sock_family=desc.sock_family, sock_type=desc.sock_type,
                    name=desc.name, port=desc.port,
                    remote_name=addr[0], remote_port=addr[1])
                csp = SocketProxy(
                    local_address=cad, socket=self, is_connected=True,
                    transport=tp)
                tp.add_connected_socket_proxy(csp)

        dc = self.data_callback
        if dc is None:
            raise NotImplementedError('No data callback specified.')

        dc(self, addr, data)


class ListenSocketProxy(SocketProxy):

    def _stream_socket_selected(self, socket):
        socket.accept()
        raise NotImplementedError()


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
            '__repr__': lambda self:
                self.__name__ + '.Transport.NameAll',
            '__doc__': (
                'Use this singleton object in your call to listen_for_me to '
                'indicate that you wish to listen on all addresses.')})()
    NameLANHostname = type(
        'ListenNameLANHostname', (), {
            '__repr__': lambda self:
                self.__name__ + '.Transport.NameLANHostname',
            '__doc__': (
                'Use this singleton object in your call to listen_for_me to '
                'indicate that you wish to listen on an address you have '
                'exposed on the Local Area Network.')})()

    NameLoopbackAddress = type(
        'ListenNameLoopbackAddress', (), {
            '__repr__': lambda self:
                self.__name__ + '.Transport.NameLoopbackAddress',
            '__doc__': (
                'Use this singleton object in your call to listen_for_me to '
                'indicate that you wish to listen on an address you have '
                'exposed on the Local Area Network.')})()

    SendFromAddressNameAny = type(
        'SendFromAddressNameAny', (), {
            '__repr__': lambda self: (
                self.__name__ + '.Transport.SendFromAddressNameAny'),
            '__doc__': (
                'Use this singleton object in your call to '
                'get_send_from_address to '
                'indicate that you wish to send from any routable '
                'local address.')})()

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

        count = 0
        for sock in self.yield_vals(self._tp_connected_sockets):
            count += 1
        return count

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

    # bind_listen_address
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

        sock_type = self.fix_sock_type(sock_type)

        provisional_laddr = ListenDescription(
            sock_family=sock_family, sock_type=sock_type, name=name,
            port=port, flowinfo=flowinfo, scopeid=scopeid,
            port_filter=port_filter)

        tpl = self.convert_listen_description_into_find_tuple(
            provisional_laddr)
        path, lsck = self.find_cached_object(self._tp_listen_sockets, tpl)
        if lsck is not None:
            raise SocketInUseError(
                'All sockets matcing Description %s are already in use.' % (
                    provisional_laddr))

        lsck = self.create_listen_socket(provisional_laddr, callback)

        return lsck.local_address

    # connect
    def get_send_from_address(
            self, sock_type=None, sock_family=None,
            name=SendFromAddressNameAny, port=0, flowinfo=0, scopeid=0,
            remote_name=None, remote_port=None, port_filter=None,
            data_callback=None,
            from_description=None, to_description=None):

        if sock_family is None:
            sock_family = IPAddressFamilyFromName(abytes(remote_name))

        create_kwargs = {}
        for attr in (
                'sock_type', 'sock_family', 'name', 'port', 'flowinfo',
                'scopeid', 'port_filter'):

            if from_description is not None:
                assert 0
                val = getattr(from_description, attr, None)
                if val is not None:
                    log.debug('Use from_description\'s %r value', attr)
                    create_kwargs[attr] = val
                    continue

            create_kwargs[attr] = locals()[attr]

        for remote_attr, to_desc_attr in (
                ('remote_name', 'name'), ('remote_port', 'port')):

            if to_description is not None:
                assert 0
                val = getattr(to_description, to_desc_attr, None)
                if val is not None:
                    log.debug('Use to_description\'s %r value', remote_attr)
                    create_kwargs[remote_attr] = val
                    continue

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

        log.debug('Cache dict: %r', cache_dict)
        log.debug('Find tuple: %r', [_item[0] for _item in find_tuple])
        full_path_len = len(find_tuple)
        path = [
            (key, obj) for key, obj in self.yield_dict_path(
                cache_dict, find_tuple)]

        log.debug(
            'Path is %d long, full find tuple is %d long', len(path),
            full_path_len)

        assert len(path) <= full_path_len
        if len(path) == full_path_len:
            lsck = path[-1][1]
            log.debug('Found object %r', lsck)
            return path, lsck
        return path, None

    def release_listen_address(self, listen_address):
        log.debug('Release %r', listen_address)
        if not isinstance(listen_address, ListenDescription):
            raise TypeError(
                'Cannot release something which is not a ListenDescription: %r' % (
                    listen_address))

        path, lsck = self.find_cached_object(
            self._tp_listen_sockets,
            self.convert_listen_description_into_find_tuple(listen_address))
        if lsck is None:
            raise KeyError(
                '%r was not a known ListenDescription.' % (listen_address))

        lsck.release()
        if not lsck.is_retained:
            log.debug('Listen address no longer retained')
            ldict = path[-2][1]
            key = path[-1][0]
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
        if not ValidPortNum(port):
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

    #
    # =================== SOCKET INTERFACE ====================================
    #
    def new_connection(self, connection_proxy):
        assert 0
        callback

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

    @classmethod
    def yield_vals(cls, root_dict):

        for key, val in iteritems(root_dict):
            if val is None:
                continue

            if isinstance(val, dict):
                for sock in cls.yield_vals(val):
                    yield sock
                continue

            yield val

    def fix_sock_family(self, sock_family):
        if sock_family is None:
            raise NotImplementedError(
                'Currently you must specify an IP family.')
        if sock_family not in SOCK_FAMILIES:
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

    #
    # =================== OLD DEPRECATED METHOD ===============================
    #

    def addDgramSocket(self, sck):
        assert 0
        self._tp_dGramSockets[sck.getsockname()] = sck
        log.debug("%r Dgram sockets now: %r", self, self._tp_dGramSockets)

    def _sendDgramMessageFrom(self, msg, toAddr, fromAddr):
        """:param msg: The message (a bytes-able) to send.
        :param toAddr: The place to send to. This should be *post* address
        resolution, so this must be either a 2 (IPv4) or a 4 (IPv6) tuple.
        """
        assert 0
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

    def listenDgram(self, lAddrName, port, port_filter):
        assert 0
        sock = GetBoundSocket(None, SOCK_DGRAM, (lAddrName, port), port_filter)
        rt = self._tp_retryThread
        rt.addInputFD(sock, WeakMethod(self, "dgramDataAvailable"))
        self.addDgramSocket(sock)
        return sock.getsockname()

    def sendMessage(self, msg, toAddr, fromAddr=None, sockType=None):
        assert 0
        sockType = self.fix_sock_type(sockType)
        if sockType == SOCK_DGRAM:
            return self._sendDgramMessage(msg, toAddr, fromAddr)

        return self.sendStreamMessage(msg, toAddr, fromAddr)

    def _sendDgramMessage(self, msg, toAddr, fromAddr):
        assert 0
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

                return
            except socket.error as exc:
                log.debug(
                    "Could not sendto %r from %r: %s", toAddr,
                    sname, exc)
        else:
            raise exc

    def dgramDataAvailable(self, sck):
        assert 0
        data, address = sck.recvfrom(4096)
        self.receivedData(sck.getsockname(), address, data)

    def receivedData(self, lAddr, rAddr, data):
        assert 0

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
        assert 0
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
