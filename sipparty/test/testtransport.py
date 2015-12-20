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
import logging
from socket import (SOCK_STREAM, SOCK_DGRAM, AF_INET, AF_INET6)
from ..transport import (ListenAddress, Transport)
from ..util import WaitFor
from .setup import (MagicMock, patch, SIPPartyTestCase)

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class TestTransport(SIPPartyTestCase):

    def setUp(self):
        super(TestTransport, self).setUp()
        self.data_call_back_call_args = []

    def data_callback(self, from_address, to_address, data):
        self.data_call_back_call_args.append((
            from_address, to_address, data))

    def new_connection(self, local_address, remote_address):
        return True

    def test_listen_address_create(self):
        log.info('ListenAddress requires a port argument')

        sock_family = AF_INET
        sock_type = SOCK_STREAM

        self.assertRaises(TypeError, ListenAddress)
        ListenAddress('somename', sock_family, sock_type, port=5060)

        log.info('Get a standard (IPv4) listen address from the transport.')
        tp = Transport()
        self.assertRaises(TypeError, tp.listen_for_me, 'not-a-callable')
        self.assertRaises(
            NotImplementedError, tp.listen_for_me, self.data_callback)
        self.assertRaises(
            ValueError, tp.listen_for_me, self.data_callback,
            sock_family=sock_family,
            sock_type='not-sock-type')
        self.pushLogLevel('transport', logging.DETAIL)
        laddr = tp.listen_for_me(self.data_callback, sock_family=sock_family)
        self.assertTrue(isinstance(laddr, ListenAddress), laddr)
        laddr2 = tp.listen_for_me(self.data_callback, sock_family=sock_family)
        self.assertIs(laddr, laddr2)

        log.info('Listening on ports %d', laddr.port)

        log.info('Release address once')
        tp.release_listen_address(laddr)
        log.info('Release address twice')
        tp.release_listen_address(laddr)
        log.info(
            'Release address thrice and get an exception as it has now been '
            'freed.')
        self.assertRaises(KeyError, tp.release_listen_address, laddr)

    def test_listen_address_receive_data(self):
        sock_family = AF_INET

        tp = Transport()
        log.info('Get a listen address')
        laddr1 = tp.listen_for_me(self.new_connection, sock_family=sock_family)

        log.info('Get send from address connected to the listen address')
        saddr = tp.get_send_from_address(
            sock_family=sock_family,
            remote_name='127.0.0.1', remote_port=laddr1.port)

        log.info('Reget the send from address and check it\'s the same one.')
        self.pushLogLevel('transport', logging.DETAIL)
        saddr2 = tp.get_send_from_address(
            sock_family=sock_family,
            remote_name='127.0.0.1', remote_port=laddr1.port)

        self.assertIs(saddr, saddr2)

        tp.send(b'hello laddr1', saddr)
        WaitFor(lambda: len(self.data_call_back_call_args) > 0)
        fromaddr, toaddr, data = self.data_call_back_call_args.pop()
        self.assertEqual(data, b'hello laddr1')
