"""
Provides a class that can be used to mock out socket.socket during UTs.

To use this, simply do::

    from sipparty.transport.mocksock import SocketMock

Then the following in your UT setUp method::

    SocketMock.test_case = self
    self.addCleanup(setattr, SocketMock, 'test_case', None)
    socket_patch = patch.object(
        transport.base, 'socket_class', spec=type, new=SocketMock)
    socket_patch.start()
    self.addCleanup(socket_patch.stop)

..
    Copyright 2016 David Park

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
from six import PY2
from .base import AF_INET, SOCK_STREAM
if PY2:
    from mock import Mock
else:
    from unittest.mock import Mock

log = logging.getLogger(__name__)


class SocketMock(object):

    _fileno = 1

    # test cases should set this in their setUp methods.
    test_case = None

    def __init__(self, family=AF_INET, type=SOCK_STREAM):
        test_case = self.test_case
        assert test_case is not None
        if getattr(test_case, 'socket_exception', None) is not None:
            raise test_case.socket_exception

        super(SocketMock, self).__init__()
        self.family = family
        self.type = type

        for attr in (
            'bind', 'listen', 'accept', 'send',
        ):
            setattr(self, attr, Mock())

        self.peer_name = getattr(test_case, 'peer_name', None)
        self.sockname = getattr(test_case, 'sockname', None)

        self._fileno = SocketMock._fileno
        SocketMock._fileno += 1

        self.read_exception = None

    def connect(self, addr_tuple):
        self.peer_name = addr_tuple
        if self.sockname is None:
            self.sockname = ('pretend-local-sockname', 12345)
        return

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
