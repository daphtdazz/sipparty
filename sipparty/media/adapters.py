"""adapters.py

Adapters for helping deal with Sessions.

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
from ..adapter import (
    AdapterOptionKeyClass, AdapterOptionKeyConversion,
    AdapterOptionKeyRecurseIf, ListConverter, ProxyAdapter)
from .session import (MediaSession, Session)
from ..sdp.sdp import (
    ConnectionDescription, MediaDescription, SessionDescription)
from ..sdp.sdpsyntax import (AddressToSDPAddrType, sock_family_to_addr_type)
from ..util import abytes


def is_none(x):
    return x is None


class MediaSessionToSDPMediaDescriptionAdapter(ProxyAdapter):
    from_class = MediaSession
    to_class = MediaDescription

    @staticmethod
    def retrieve_net_type_from_parent(parent):
        if parent is None:
            return None

        return AddressToSDPAddrType()

    adaptations = (
        ('netType', 'local_addr_description', {
            AdapterOptionKeyConversion: retrieve_net_type_from_parent}),
        ('port', 'port'),
        ('address', 'name', {
            AdapterOptionKeyConversion: abytes}),
        ('transProto', 'transProto', {
            AdapterOptionKeyConversion: abytes}),
        ('mediaType', 'media_type', {
            AdapterOptionKeyConversion: abytes}),
        ('formats', 'formats'),
        ('connectionDescription', {
            AdapterOptionKeyClass: ConnectionDescription
        })
    )


class SessionToSDPAdapter(ProxyAdapter):
    from_class = Session
    to_class = SessionDescription

    adaptations = (
        ('username', 'username', {AdapterOptionKeyConversion: abytes}),
        ('address', 'address', {
            AdapterOptionKeyConversion: abytes,
            AdapterOptionKeyRecurseIf: is_none}),
        ('mediaDescriptions', 'mediaSessions', {
            AdapterOptionKeyConversion: ListConverter(MediaDescription)}),
        ('addressType', 'sock_family', {
            AdapterOptionKeyConversion: sock_family_to_addr_type,
            AdapterOptionKeyRecurseIf: is_none})
    )


class SessionToConnectionDescriptionAdapter(ProxyAdapter):
    from_class = Session
    to_class = ConnectionDescription

    adaptations = (
        ('address', 'name', {
            AdapterOptionKeyConversion: abytes}),
        ('addressType', 'sock_family', {
            AdapterOptionKeyConversion: sock_family_to_addr_type,
            AdapterOptionKeyRecurseIf: is_none})
    )


class MediaSessionToConnectionDescriptionAdapter(ProxyAdapter):
    from_class = MediaSession
    to_class = ConnectionDescription

    adaptations = (
        ('address', 'local_addr_description', {
            AdapterOptionKeyConversion: lambda _lad:
                abytes(_lad.name)}),
        ('addressType', 'local_addr_description', {
            AdapterOptionKeyConversion: lambda _lad:
                sock_family_to_addr_type(_lad.sock_family)}),
    )
