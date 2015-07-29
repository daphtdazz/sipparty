"""transportmanager.py

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
import logging
log = logging.getLogger(__name__)


class ActiveTransportManager(object):

    sharedInstance = None

    @classmethod
    def __new__(cls, name):
        log.debug("New with class %r, name %r", cls, name)
        if cls.sharedInstance is None:
            cls.sharedInstance = super(type, cls).__new__(name)
        return cls.sharedInstance

    def AddConnectedTransport(cls, tp):
        rkey = (tp.remoteAddressHost, tp.remoteAddressPort)
        log.debug("Adding Connected Transport to %r", rkey)
        typ = tp.socketType
        lkey = (tp.localAddressHost, tp.localAddressPort)
        cis1 = cls.ConnectedInstances

        for key1, key2, key3 in (rkey, typ, lkey), (rkey, lkey, typ):
            if key1 not in cis1:
                cis1[key1] = {}

            cis2 = cis1[key1]

            if key2 not in cis2:
                cis2[key2] = {}

            cis3 = cis2[key2]

            if key3 in cis3:
                raise KeyError(
                    "Transport to %r is already taken, key %r." % (cis3[key3],
                    key3))
            cis3[key3] = tp

    @classmethod
    def GetConnectedTransport(cls, remote_addr, remote_port, local_addr=None,
                              typ=None):
        """Get a connected transport to the given address tuple.

        :param string remote_addr: The address or hostname of the target we
        want to get a connection to.
        :param integer remote_port: The port of the target we want to get a
        connection to.
        """
        assert typ is None, "typ not yet implemented"
        assert local_addr is None, "local_addr not yet implemented"
        key1 = (remote_addr, remote_port)
        cis1 = cls.ConnectedInstances
        log.debug("GetConnectedTransport to %r from all %r",
            (remote_addr, remote_port), cis1)
        if key1 in cis1:
            cis2 = cis1[key1]
            for cis3 in itervalues(cis2):
                for tp in itervalues(cis3):

                    log.debug("Got existing connected transport %r", tp)
                    return tp

        # No existing connected transport.
        return None

    @classmethod
    def RemoveConnectedTransport(cls, tp):
        rkey = (tp.remoteAddressHost, tp.remoteAddressPort)
        log.debug("Adding Connected Transport to %r", rkey)
        typ = tp.socketType
        lkey = (tp.localAddressHost, tp.localAddressPort)
        cis1 = cls.ConnectedInstances

        for it, key1, key2, key3 in (1, rkey, typ, lkey), (2, rkey, lkey, typ):

            def not_there():
                raise KeyError(
                    "No transport to %r from %r registered as connected." % (
                        key1, key2 if it == 1 else key3))

            if key1 not in cis1:
                not_there()
            cis2 = cis1[key1]

            if key2 not in cis2:
                not_there()

            cis3 = cis2[key2]

            if key3 not in cis3:
                not_there()
            del cis3[key3]

            if len(cis3) == 0:
                del cis2[key2]

            if len(cis2) == 0:
                del cis1[key1]
