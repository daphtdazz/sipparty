"""mediatransport.py

Specializes the transport layer for media.

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
from six import (binary_type as bytes, itervalues)
import logging
from sipparty.transport import Transport

log = logging.getLogger(__name__)


class MediaTransport(Transport):

    def __new__(cls, *args, **kwargs):
        if "singleton" not in kwargs:
            kwargs["singleton"] = "Media"
        return super(MediaTransport, cls).__new__(cls, *args, **kwargs)

    def __init__(self):
        super(MediaTransport, self).__init__()
        self.byteConsumer = self.mediaByteConsumer

    def mediaByteConsumer(self, lAddr, rAddr):
        pass
