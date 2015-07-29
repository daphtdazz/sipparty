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

from sipparty import (util, vb)
import prot
import transport
import message
import collections

log = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class SIPMessageConsumer(object):
    @abc.abstractmethod
    def messageConsumer(self):
        raise AttributeError("messageConsumer not implemented for class %r" % (
            self.__class__.__name__))


class SipTransport(transport.ActiveTransport):

    #
    # =================== CLASS INTERFACE ====================================
    #
    MessageConsumers = {}

    # These are cumulative with the super classes'.
    States = util.Enum(
        ("sendingreq", "waitingrsp"))

    @classmethod
    def AddClassTransitions(cls):
        log.debug("STFSM's states: %r", cls.States)
        super(cls, cls).AddClassTransitions()

    @classmethod
    def RegisterMessageConsumer(cls, key, consumer):
        """
        :param tuple key: Of the form (call_id, local_tag, remote_tag), where
        each value is the string value.
        """
        if not isinstance(consumer, SIPMessageConsumer):
            raise TypeError(
                "%r instance is not an instance of SIPMessageConsumer." % (
                    consumer.__class__.__name__,))

        assert key not in cls.MessageConsumers
        cls.MessageConsumers[key] = consumer

    #
    # =================== INSTANCE INTERFACE =================================
    #
    messages = util.DerivedProperty("_tsipfsm_messages")
    messageConsumer = util.DerivedProperty(
        "_tsipfsm_messageConsumer",
        lambda val: isinstance(val, collections.Callable))

    def __init__(self, **kwargs):
        super(SipTransport, self).__init__(**kwargs)

        self._tsipfsm_messageConsumer = None
        self._tsipfsm_messages = []

        self.byteConsumer = util.WeakMethod(
            self, "_tsfsm_consumeBytes", default_rc=0)

    #
    # =================== INTERNAL ===========================================
    #
    def _tsfsm_consumeBytes(self, data):
        log.debug(
            "SipTransport attempting to consume %d bytes.", len(data))
        log.debug("%r", data)

        # SIP messages always have \r\n\r\n after the headers and before any
        # bodies.
        eoleol = prot.EOL * 2

        eoleol_index = data.find(eoleol)
        if eoleol_index == -1:
            # No possibility of a full message yet.
            log.debug("Data not a full SIP message.")
            return 0

        # We've got a full message, so parse it.
        newmessage = message.Message.Parse(data)
        message_end = eoleol_index + len(eoleol)

        self.messages.append(newmessage)
        if self.messageConsumer is not None:
            self.messageConsumer(newmessage)

        return message_end


class SipListenTransport(transport.ListenTransport):
    ConnectedTransportClass = SipTransport
