"""
Overview
--------
The :py:module:`transport` package is high-level API for working with sockets.

The key class is the :py:class:`Transport`. Through it you request listen
sockets and connected sockets, for which you provide an :py:class:`SocketOwner`
instance that will be called back on a background thread when events happen
on the socket.


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

from .base import (
    SOCK_TYPES, SOCK_TYPES_NAMES, SOCK_TYPE_IP_NAMES, SOCK_FAMILIES,
    SOCK_FAMILY_NAMES, DEFAULT_SOCK_FAMILY,
    digitrange, DIGIT, HEXDIG, IPv4address,
    IPv6address, IPaddress, port, hex4_re, IPv4address_re, IPv4address_only_re,
    IPv6address_re, IPv6address_only_re, IPaddress_re, IPaddress_only_re,
    NameAll, NameLANHostname, NameLoopbackAddress, SendFromAddressNameAny,
    SpecialNames, address_as_tuple, AllAddressesFromFamily, default_hostname,
    IPAddressFamilyFromName, is_null_address, IsSpecialName, IsValidPortNum,
    IsValidTransportName, LoopbackAddressFromFamily, UnregisteredPortGenerator,
    TransportException, BadNetwork, SocketInUseError, SockFamilyName,
    SockTypeName, SockTypeFromName,
    GetBoundSocket,
    ListenDescription, ConnectedAddressDescription,
    SocketOwner,
    SocketProxy,
    Transport
)

__all__ = [name for name in dict(locals())]
