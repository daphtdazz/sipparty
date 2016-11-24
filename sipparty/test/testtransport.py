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
from select import error as select_error
from six.moves.queue import Queue
from socket import (
    error as sock_error, SOCK_DGRAM, SOCK_STREAM, AF_INET, AF_INET6)
from .. import transport
from ..fsm import retrythread
from ..fsm.retrythread import RetryThread
from ..transport import (
    address_as_tuple, ConnectedAddressDescription,
    is_null_address, ListenDescription,
    NameAll, SendFromAddressNameAny, SocketOwner,
    SocketProxy, Transport, IPv6address_re,
    IPv6address_only_re)
from ..util import WaitFor
from .base import (Mock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)


class TestTransport(SocketOwner, SIPPartyTestCase):

    def consume_data(self, proxy, remote_address, data):
        self.data_call_back_call_args.append((proxy, remote_address, data))

    def setUp(self):
        super(TestTransport, self).setUp()
        self.data_call_back_call_args = []

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
        self.assertRaises(ValueError, tp.listen_for_me, 'not-a-SockOwner')
        self.assertRaises(
            ValueError, tp.listen_for_me, None,
            sock_family=sock_family,
            sock_type='not-sock-type')

        laddr = tp.listen_for_me(
            self, sock_family=sock_family, sock_type=sock_type,
            port=0)
        self.assertTrue(isinstance(laddr, ListenDescription), laddr)

        log.info('Listen a second time and reuse existing')
        laddr2 = tp.listen_for_me(
            self, sock_family=sock_family, sock_type=sock_type,
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
            self, sock_family=sock_family, sock_type=sock_type,
            port=0)
        laddr2 = tp.listen_for_me(
            self, sock_family=sock_family, sock_type=sock_type,
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
        laddr_desc = tp.listen_for_me(self, sock_family=sock_family)

        log.info('Get send from address connected to the listen address')
        conn_sock_proxy = tp.get_send_from_address(
            sock_family=sock_family,
            remote_name='127.0.0.1', remote_port=laddr_desc.port,
            owner=self)

        self.assertIs(conn_sock_proxy.transport, tp)

        # At this point we should have two connected sockets if TCP, one on
        # UDP. That's because we only detect a new UDP 'connection' when we
        # have first received data on it.
        self.assertEqual(tp.connected_socket_count, 1)

        log.info('Reget the send from address and check it\'s the same one.')
        second_conn_sock_proxy = tp.get_send_from_address(
            remote_name='127.0.0.1', remote_port=laddr_desc.port,
            owner=self)

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
            owner=self)

        log.info('Send data back on the new connection.')
        lstn_conn_sock_proxy = tp.get_send_from_address(
            remote_name=conn_sock_proxy.local_address.name,
            remote_port=conn_sock_proxy.local_address.port,
            owner=self)

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
        lprx = laddr.listen(tp, self)

        log.info('Create cad')
        cad = ConnectedAddressDescription(
            remote_name='127.0.0.1',
            name=SendFromAddressNameAny, sock_type=SOCK_DGRAM)

        # ValueError since remote_port is None
        self.assertRaises(TypeError, cad.connect, lambda x: None, tp)

        log.info('Connect cad')
        cad.remote_port = lprx.local_address.port
        cprx = cad.connect(tp, type('AdhocSocketOwner', (SocketOwner,), {
            'consume_data': lambda *args: None
        })())
        tp.add_connected_socket_proxy(cprx)

        log.info('Re-find connected proxy with %s', cad)
        cprx2 = tp.find_or_create_send_from_socket(cad, None)
        self.assertIs(cprx, cprx2)


class TestTransportErrors(SIPPartyTestCase):

    def retry_thread_select(self, in_, out, error, wait):
        assert wait >= 0

        if self.finished:
            return [], [], []

        if self.select_fd_error is not None:
            fd, error_ = self.select_fd_error
            if fd in list(in_) + list(out) + list(error):
                log.info('Raising select exception')
                self.sel_exceptions_raised += 1
                raise error_
            return [], [], []

        log.debug('Test select getting next item')
        self.sel_queueing = True
        res = self.sel_queue.get()
        self.sel_queueing = False

        if res is None:
            self.finished = True
            res = [], [], []

        if isinstance(res, Exception):
            raise res

        log.debug('Test select yielding %s' % (res,))
        return res

    def setUp(self):
        super(TestTransportErrors, self).setUp()

        self.finished = False
        self.sel_queue = Queue()
        self.select_fd_error = None
        self.sel_queueing = False
        self.sel_exceptions_raised = 0
        self.addCleanup(lambda: self.sel_queue.put(None))

        select_patch = patch.object(
            retrythread, 'select', new=self.retry_thread_select)
        select_patch.start()
        self.addCleanup(select_patch.stop)

        self.socket_exception = None
        test_case = self

        class SocketMock(object):

            _fileno = 1

            def __init__(self, family=AF_INET, type=SOCK_STREAM):
                if test_case.socket_exception is not None:
                    raise test_case.socket_exception

                super(SocketMock, self).__init__()
                self.family = family
                self.type = type

                for attr in (
                    'connect', 'bind', 'listen', 'accept', 'send',
                ):
                    setattr(self, attr, Mock())

                for attr in ('peer_name', 'sockname'):
                    setattr(self, attr, getattr(test_case, attr))

                self._fileno = SocketMock._fileno
                SocketMock._fileno += 1

                self.read_exception = None

            def close(self):
                pass

            def fileno(self):
                return self._fileno

            def getpeername(self):
                return self.peer_name

            def getsockname(self):
                return self.sockname

            def recv(self, numbytes):
                log.debug('sock mock recv numbytes %d', numbytes)
                if self.read_exception is not None:
                    raise self.read_exception
                data = self.data
                del self.data
                return data

            def recvfrom(self, numbytes):
                log.debug('sock mock recvfrom numbytes %d', numbytes)
                return self.recv(numbytes), self.getpeername()

        socket_patch = patch.object(
            transport.base, 'socket_class', spec=type, new=SocketMock)
        socket_patch.start()
        self.addCleanup(socket_patch.stop)

        self.socket = RuntimeError('No socket configured')

    def tearDown(self):
        self.sel_queue.put(None)
        log.info('None put on queue')
        super(TestTransportErrors, self).tearDown()

    def test_socket_proxy_wr(self):

        sp = SocketProxy()

        tp = Transport()
        sp.transport = tp

        owner = type('AdhocOwner', (SocketOwner,), {
            'consume_data': lambda *args, **kwargs: None})()
        sp.owner = owner

        self.assertIsNotNone(sp.transport)
        self.assertIsNotNone(sp.owner)
        del tp
        del owner
        self.assertIsNone(sp.transport)
        self.assertIsNone(sp.owner)

    def test_mock_socket_exception(self):
        """Test that the mock socket can connect and "send" data."""
        log.info('Create Transport')
        tp = Transport()

        log.info('Get a connected socket')

        # configure the socket we'll get
        self.peer_name = ('127.0.0.5', 12480)
        self.sockname = ('mock-sock', 55555)

        ds = Mock(spec=SocketOwner)
        ds.consume_data = Mock()
        ds.handle_terminal_socket_exception = Mock()

        sprxy = tp.get_send_from_address(
            remote_name=self.peer_name[0], remote_port=self.peer_name[1],
            name=SendFromAddressNameAny, sock_type=SOCK_DGRAM,
            owner=ds)

        # Spin the retrythread because we need to pick up the new socket.
        self.sel_queue.put(([], [], []))

        log.info('Put data on the socket')
        sprxy.socket.data = b'some data'
        self.sel_queue.put(([sprxy.socket.fileno()], [], []))

        WaitFor(lambda: ds.consume_data.call_count > 0, timeout_s=0.2)
        self.assertEqual(ds.consume_data.call_count, 1)
        ds.consume_data.assert_called_with(sprxy, self.peer_name, b'some data')

        log.info('Cause an exception on the socket when reading')
        exc = type('SocketException', (sock_error,), {})(
            'Test socket exception')
        sprxy.socket.read_exception = exc

        self.sel_queue.put(([sprxy.socket.fileno()], [], []))
        WaitFor(
            lambda: ds.handle_terminal_socket_exception.call_count > 0,
            timeout_s=0.2)
        self.assertEqual(ds.handle_terminal_socket_exception.call_count, 1)
        ds.handle_terminal_socket_exception.assert_called_with(sprxy, exc)
        self.assertEqual(ds.consume_data.call_count, 1)

        log.info('Test complete')

    def test_select_exception(self):

        rt = RetryThread()

        WaitFor(lambda: self.sel_queueing)

        # There may be other private fds on the rt so find one.
        for fd in range(1, 100):
            try:
                rt.addInputFD(fd, lambda x: None)
                break
            except KeyError:
                pass
        else:
            assert 0
        self.assertRaises(KeyError, rt.addInputFD, fd, lambda x: None)

        self.select_fd_error = (fd, select_error('error on %d' % fd))
        log.info('Trigger select')
        self.sel_queue.put(([], [], []))

        # On next select call, the fd error will be triggered. retrythread
        # will then attempt to determine which fd was the issue, will work
        # out that it was fd by doing another select, and then
        # move it to the dead queue.
        WaitFor(lambda: self.sel_exceptions_raised == 2)
        self.select_fd_error = None
        WaitFor(lambda: self.sel_queueing)

        # It should still be not possible to add the fd since it's still on the
        # thread, just in the dead set.
        self.assertRaises(KeyError, rt.addInputFD, fd, lambda x: None)

        # We can now remove it.
        rt.rmInputFD(fd)
        self.assertRaises(KeyError, rt.rmInputFD, fd)
