"""Implements the `Party` object.

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

from ..util import Enum

log = logging.getLogger(__name__)


class StandardTimers:
    """Mixin class for FSMs that need to use standard SIP timers."""

    # Default timer durations (seconds)
    T1 = 0.5
    T2 = 4
    T4 = 5

    names = Enum((
        'standard_timer_retransmit_gen', 'standard_timer_giveup_gen',
        'standard_timer_stop_squelching_gen'))

    def standard_timer_retransmit_gen(self):
        """Yield intervals for standard retransmit timer as per RFC3261.

        https://tools.ietf.org/html/rfc3261#section-17.2.1

        After parsing that, the algorithm turns out to be quite simple.
        """
        t1 = self.T1
        t2 = self.T2

        # To avoid these generators delaying release of self, delete it.
        del self
        next_interval = t1
        while True:
            yield next_interval
            next_interval *= 2
            next_interval = min(next_interval, t2)

    def standard_timer_giveup_gen(self):
        """Yield the standard giveup interval as per RFC3261.

        https://tools.ietf.org/html/rfc3261#section-17.2.1
        """
        t1 = self.T1
        # To avoid these generators delaying release of self, delete it.
        del self
        yield 64 * t1

    def standard_timer_stop_squelching_gen(self):
        """Yield the giveup interval for timer I as per RFC3261.

        https://tools.ietf.org/html/rfc3261#section-17.2.1
        """
        t4 = self.T4
        del self
        yield t4
