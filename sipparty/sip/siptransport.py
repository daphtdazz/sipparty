"""siptransport.py

Specializes the transport layer for SIP.

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
import abc
import logging
import socket

from sipparty import (util, vb)
import prot
import message
import collections

log = logging.getLogger(__name__)
bytes = six.binary_type
itervalues = six.itervalues


class SIPSocket(object):

    @property
    def fromAddr(self):
        return self._ssck_sock.getpeername()

    def __init__(self, sockType, toAddr, fromAddr=None):

        if isinstance(toAddr, bytes):
            toAddr = (toAddr, 0)

        addrinfos = socket.getaddrinfo(toAddr[0], toAddr[1], )

        sock = socket.socket(socket.AF_INET, sockType)

        if fromAddr is not None:
            log.debug("Bind socket to %r", fromAddr)
            sock.bind(fromAddr)
        self._ssck_sock = sock

class SIPTransport(object):

    DefaultType = socket.SOCK_DGRAM

    def __init__(self):
        self._sptr_socketsByType = {
            socket.SOCK_STREAM: {}, socket.SOCK_DGRAM: {}}
        super(SIPTransport, self).__init__()

    def send(self, data, toAddr, fromAddr=None, sockType=None):
        if sockType is None:
            sockType = self.DefaultType
        sck = self.socket(sockType, toAddr, fromAddr, create=True)
        sck.send(data)

    def socket(self, sockType, toAddr, fromAddr, create=False):
        if fromAddr is not None:
            log.debug(
                "Get specific socket to %r from %r type %r", toAddr, fromAddr,
                sockType)
            return self._sptr_specificSocket(
                sockType, toAddr, fromAddr, create)

        log.debug("Get any socket to %r type %r", toAddr, sockType)
        return self._sptr_anySocketTo(sockType, toAddr, create)

    def _sptr_specificSocket(self, sockType, toAddr, fromAddr, create):
        scksByFrom = self._sptr_socketsTo(sockType, toAddr, create)
        if scksByFrom is None:
            return None

        if fromAddr not in scksByFrom:
            if not create:
                log.debug("No socket to %r from %r", toAddr, fromAddr)
                return None
            log.debug("New socket to %r from %r", toAddr, fromAddr)
            sck = SIPSocket(sockType, toAddr, fromAddr)
            scksByFrom[fromAddr] = sck

        sck = scksByFrom[fromAddr]
        log.debug("Existing socket to %r from %r", toAddr, fromAddr)
        return sck

    def _sptr_anySocketTo(self, sockType, toAddr, create):
        scksByFrom = self._sptr_socketsTo(sockType, toAddr, create)
        if scksByFrom is None:
            return None

        for sck in itervalues(scksByFrom):
            log.debug("Existing socket to %r", toAddr)
            return sck

        if not create:
            log.debug("No active socket to %r", toAddr)
            return None

        log.debug("Create new socket to %r", toAddr)
        sck = SIPSocket(sockType, toAddr)
        fromAddr = sck.fromAddr
        log.debug("Socket from address is %r", fromAddr)
        scksByFrom[fromAddr] = sck
        return sck

    def _sptr_socketsTo(self, sockType, toAddr, create):
        typeScksByTo = self._sptr_socksForType(sockType)
        if toAddr not in typeScksByTo:
            if not create:
                log.debug("No socket to %r", toAddr)
                return None
            log.debug("Create sockets to %r", toAddr)
            scks = {}
            typeScksByTo[toAddr] = scks
            return scks

        return typeScksByTo[toAddr]

    def _sptr_socksForType(self, sockType=None):
        if sockType is None:
            sockType = self.DefaultType
        scksByType = self._sptr_socketsByType
        if sockType not in scksByType:
            raise ValueError("Can't send to bad socket type %r" % sockType)

        return scksByType[sockType]
