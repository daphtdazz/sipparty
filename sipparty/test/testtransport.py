"""ttransport.py

Unit tests for the transport code.

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

import logging
from queue import Queue
from socket import (socket, SOCK_DGRAM, SOCK_STREAM, AF_INET, AF_INET6)
from .. import transport
from ..fsm import retrythread
from ..transport import (
    address_as_tuple, ConnectedAddressDescription,
    is_null_address, ListenDescription,
    NameAll, SendFromAddressNameAny,
    SocketProxy, Transport, IPv6address_re,
    IPv6address_only_re)
from ..util import WaitFor
from .base import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestTransport(SIPPartyTestCase):

    def setUp(self):
        super(TestTransport, self).setUp()
        self.data_call_back_call_args = []

    def data_callback(self, from_address, to_address, data):
        self.data_call_back_call_args.append((
            from_address, to_address, data))

    def new_connection(self, local_address, remote_address):
        return True

    def test_ip_addresses(self):
        for ip6_string in (
                b'::1', b'::', b'fe80::1', b'fe80:1:1:1:1:1:1:1',
                b'fe80::aa66:7fff:FE0e:f035', b'fe80::', b'1:2:3:4:5:6:7::'):
            mo = IPv6address_re.match(ip6_string)
            self.assertIsNotNone(mo)
            self.assertEqual(mo.group(0), ip6_string)

            # Should get the same results with an exact match.
            mo = IPv6address_only_re.match(ip6_string)
            self.assertIsNotNone(mo)
            self.assertEqual(mo.group(0), ip6_string)

        for bad_ip6_addr in (
                b'fe80::1::1', b':::', b'1:2:3:4:5:6:7:8:9',
                b'1:2:3::5:6:7:8:9', b'1::3:4:5:6:7:8:9', b'1::3:4:5:6:7:8:',
                b'1:2:3:4:5:6:7::9'):
            mo = IPv6address_only_re.match(bad_ip6_addr)
            self.assertIsNone(mo)

        for contains_ip_addr, offset, length in (
                (b'fe80::aa66:7fff:fe0e:f035%en0', 0, 25),):
            mo = IPv6address_re.match(contains_ip_addr)
            self.assertIsNotNone(mo)
            self.assertEqual(mo.group(0), contains_ip_addr[offset:length])

    def test_transport_data_structures(self):
        log.info('Test transport data structures')
        tp = Transport()
        ad = ConnectedAddressDescription(
            name='0.0.0.0', sock_family=AF_INET, sock_type=SOCK_STREAM,
            remote_name='127.0.0.1', remote_port=54321)
        sp = SocketProxy(local_address=ad, transport=tp)
        tp.add_connected_socket_proxy(sp)
        self.assertEqual(tp.connected_socket_count, 1)

        ad = ConnectedAddressDescription(
            name='0.0.0.0', sock_family=AF_INET, sock_type=SOCK_STREAM,
            remote_name='127.0.0.1', remote_port=54322)
        sp = SocketProxy(local_address=ad, transport=tp)

        log.info('Add second connected socket proxy, make sure it is saved.')
        tp.add_connected_socket_proxy(sp)
        self.assertEqual(tp.connected_socket_count, 2)

        log.info('Check descriptions can deduce some values.')
        ld = ListenDescription(name='1.1.1.1')
        self.assertEqual(ld.sock_family, None)
        ld.deduce_missing_values()
        self.assertEqual(ld.sock_family, AF_INET)

        ld = ListenDescription(name='::1:2:3:4')
        self.assertIs(ld.flowinfo, None)
        self.assertIs(ld.scopeid, None)
        ld.deduce_missing_values()
        self.assertEqual(ld.sock_family, AF_INET6)
        self.assertEqual(ld.flowinfo, 0)
        self.assertEqual(ld.scopeid, 0)

    def test_listen_address_create(self):
        log.info('ListenDescription requires a port argument')

        sock_family = AF_INET
        sock_type = SOCK_STREAM

        log.info('Get a standard (IPv4) listen address from the transport.')
        tp = Transport()
        self.assertRaises(TypeError, tp.listen_for_me, 'not-a-callable')
        self.assertRaises(
            ValueError, tp.listen_for_me, self.data_callback,
            sock_family=sock_family,
            sock_type='not-sock-type')

        laddr = tp.listen_for_me(
            self.data_callback, sock_family=sock_family, sock_type=sock_type,
            port=0)
        self.assertTrue(isinstance(laddr, ListenDescription), laddr)

        log.info('Listen a second time and reuse existing')
        laddr2 = tp.listen_for_me(
            self.data_callback, sock_family=sock_family, sock_type=sock_type,
            port=0)
        self.assertEqual(laddr2.sockname_tuple, laddr.sockname_tuple)

        log.info('Release address once')
        tp.release_listen_address(laddr)

        log.info('Release address twice')
        tp.release_listen_address(laddr)
        log.info(
            'Release address three times and get an exception as it has now '
            'been freed.')

        self.assertRaises(KeyError, tp.release_listen_address, laddr)

    def test_no_socket_reuse(self):
        self.skipTest('Not reusing sockets not properly supported yet.')
        sock_family = AF_INET
        sock_type = SOCK_STREAM
        tp = Transport()

        log.info("Listen twice but don't reuse socket")
        laddr = tp.listen_for_me(
            self.data_callback, sock_family=sock_family, sock_type=sock_type,
            port=0)
        laddr2 = tp.listen_for_me(
            self.data_callback, sock_family=sock_family, sock_type=sock_type,
            reuse_socket=False)
        self.assertEqual(tp.listen_socket_count, 2)

        tp.release_listen_address(laddr2)
        self.assertRaises(KeyError, tp.release_listen_address, laddr2)
        self.assertEqual(tp.listen_socket_count, 1)
        tp.release_listen_address(laddr)
        self.assertRaises(KeyError, tp.release_listen_address, laddr)

    def test_listen_address_receive_data(self):
        sock_family = AF_INET

        log.info('Get a listen address')
        tp = Transport()
        laddr_desc = tp.listen_for_me(
            self.data_callback, sock_family=sock_family)

        log.info('Get send from address connected to the listen address')
        conn_sock_proxy = tp.get_send_from_address(
            sock_family=sock_family,
            remote_name='127.0.0.1', remote_port=laddr_desc.port,
            data_callback=self.data_callback)

        self.assertIs(conn_sock_proxy.transport, tp)

        # At this point we should have two connected sockets if TCP, one on
        # UDP. That's because we only detect a new UDP 'connection' when we
        # have first received data on it.
        self.assertEqual(tp.connected_socket_count, 1)

        log.info('Reget the send from address and check it\'s the same one.')
        second_conn_sock_proxy = tp.get_send_from_address(
            remote_name='127.0.0.1', remote_port=laddr_desc.port,
            data_callback=self.data_callback)

        self.assertIs(conn_sock_proxy, second_conn_sock_proxy)
        del second_conn_sock_proxy

        self.assertEqual(tp.connected_socket_count, 1)

        conn_sock_proxy.send(b'hello laddr_desc')
        WaitFor(lambda: len(self.data_call_back_call_args) > 0)

        fromaddr, toaddr, data = self.data_call_back_call_args.pop()
        self.assertEqual(data, b'hello laddr_desc')
        self.assertEqual(tp.connected_socket_count, 2)

        # Type Error because using a bad remote_port type.
        self.assertRaises(
            TypeError, tp.get_send_from_address,
            remote_port=conn_sock_proxy.local_address,
            data_callback=self.data_callback)

        log.info('Send data back on the new connection.')
        lstn_conn_sock_proxy = tp.get_send_from_address(
            remote_name=conn_sock_proxy.local_address.name,
            remote_port=conn_sock_proxy.local_address.port,
            data_callback=self.data_callback)

        lstn_conn_sock_proxy.send(b'hello other')
        WaitFor(lambda: len(self.data_call_back_call_args) > 0)
        fromaddr, toaddr, data = self.data_call_back_call_args.pop()
        self.assertEqual(data, b'hello other')

    def test_parsing_ip_addresses(self):

        for bad_name in ('not-an-ip', 'fe80::1::1'):
            self.assertRaises(ValueError, address_as_tuple, bad_name)
            self.assertIsNone(address_as_tuple(
                bad_name, raise_on_non_ip_addr_name=False))

        for not_null in ('not-an-ip', 'fe80::1', 'fe80::1::1'):
            self.assertFalse(is_null_address(not_null))

        for null in ('0.0.0.0', '::', '0:0:0:0:0:0:0:0'):
            self.assertTrue(is_null_address(null))

        for valid_not_null in ('not-an-ip', '::1'):
            self.assertFalse(is_null_address(valid_not_null))

        for inp, out in (
                ('127.0.0.1', (127, 0, 0, 1)),
                ('0.0.0.0', (0, 0, 0, 0)),
                ('fe80:12:FFFF::', (0xfe80, 0x12, 0xffff, 0, 0, 0, 0, 0)),
                ('fe80::1', (0xfe80, 0, 0, 0, 0, 0, 0, 1)),
                ('::1', (0, 0, 0, 0, 0, 0, 0, 1)),
                ('::', (0, 0, 0, 0, 0, 0, 0, 0)),):
            self.assertEqual(address_as_tuple(inp), out)

    def test_listen_dgram_dont_connect(self):
        tp = Transport()
        laddr = ListenDescription(
            name=NameAll, sock_family=AF_INET6, sock_type=SOCK_DGRAM)
        lprx = laddr.listen(lambda x: None, tp)

        log.info('Create cad')
        cad = ConnectedAddressDescription(
            remote_name='127.0.0.1',
            name=SendFromAddressNameAny, sock_type=SOCK_DGRAM)

        # ValueError since remote_port is None
        self.assertRaises(TypeError, cad.connect, lambda x: None, tp)

        log.info('Connect cad')
        cad.remote_port = lprx.local_address.port
        cprx = cad.connect(lambda x: None, tp)
        tp.add_connected_socket_proxy(cprx)

        log.info('Re-find connected proxy with %s', cad)
        cprx2 = tp.find_or_create_send_from_socket(cad, None)
        self.assertIs(cprx, cprx2)


class TestTransportErrors(SIPPartyTestCase):

    def retry_thread_select(self, in_, out, error, wait):
        assert wait >= 0

        if self.finished:
            return [], [], []

        res = self.sel_queue.get()
        if res is None:
            self.finished = True
            res = [], [], []

        return res

    def setUp(self):
        super(TestTransportErrors, self).setUp()

        self.finished = False
        self.sel_queue = Queue()
        self.addCleanup(lambda: self.sel_queue.put(None))

        select_patch = patch.object(
            retrythread, 'select', new=self.retry_thread_select)
        select_patch.start()
        self.addCleanup(select_patch.stop)

        self.socket_exception = None
        test_case = self

        class SocketMock(socket):

            _fileno = 1

            def __init__(self, *args, **kwargs):
                if test_case.socket_exception is not None:
                    raise test_case.socket_exception

                super(SocketMock, self).__init__(*args, **kwargs)

                for attr in (
                    'connect', 'bind', 'listen', 'accept', 'send',
                ):
                    setattr(self, attr, MagicMock())

                for attr in ('peer_name', 'sockname'):
                    setattr(self, attr, getattr(test_case, attr))

                self._fileno = SocketMock._fileno
                SocketMock._fileno += 1

            def fileno(self):
                return self._fileno

            def getpeername(self):
                return self.peer_name

            def getsockname(self):
                return self.sockname

            def recv(self, numbytes):
                return self.data

            def recvfrom(self, numbytes):
                return self.data, self.getpeername()

        socket_patch = patch.object(
            transport, 'socket_class', spec=type, new=SocketMock)
        socket_patch.start()
        self.addCleanup(socket_patch.stop)

        self.socket = RuntimeError('No socket configured')

    def tearDown(self):
        self.sel_queue.put(None)
        super(TestTransportErrors, self).tearDown()

    def test_mock_socket_read(self):
        """Test that the mock socket can connect and "send" data."""
        log.info('Create Transport')
        tp = Transport()

        log.info('Get a connected socket')

        # configure the socket we'll get
        self.peer_name = ('127.0.0.5', 12480)
        self.sockname = ('mock-sock', 55555)

        ds = MagicMock()

        sprxy = tp.get_send_from_address(
            remote_name=self.peer_name[0], remote_port=self.peer_name[1],
            name=SendFromAddressNameAny, sock_type=SOCK_DGRAM,
            data_callback=ds)

        # Spin the retrythread because we need to pick up the new socket.
        self.sel_queue.put(([], [], []))

        sprxy.socket.data = b'some data'
        self.sel_queue.put(([sprxy.socket.fileno()], [], []))

        WaitFor(lambda: ds.call_count == 1, timeout_s=0.2)
        ds.assert_called_with(sprxy, self.peer_name, sprxy.socket.data)
