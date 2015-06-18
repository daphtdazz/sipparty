"""scenario.py

A scenario is basically just an FSM with a set of inputs that can match SIP
methods.

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
import six
import copy
import unittest

from sipparty import(fsm,)
import request
import weakref
import collections

log = logging.getLogger(__name__)

TransitionKeys = copy.copy(fsm.TransitionKeys)
tks = TransitionKeys  # Short alias
InitialStateKey = fsm.InitialStateKey


def ScenarioClassWithDefinition(name, defn):
    nc = type(name + "Scenario", (Scenario,), {})
    nc.PopulateWithDefinition(defn)
    return nc


class Scenario(fsm.FSM):

    DelegateResetMethod = "scenarioDelegateReset"

    @classmethod
    def PopulateWithDefinition(cls, definition_dict):
        log.debug("Populate scenario with definition.")
        new_dict = dict(definition_dict)

        # Normalize message names in the dictionary and add action based on
        # message.
        for state, stdict in six.iteritems(new_dict):
            for name, val in six.iteritems(dict(stdict)):
                if name in request.Request.types:
                    nn = getattr(request.Request.types, name)
                    if nn != name:
                        stdict[nn] = val
                        del stdict[name]

        super(Scenario, cls).PopulateWithDefinition(definition_dict)

    def __init__(self, transform=None, transitions=None, **kwargs):
        super(Scenario, self).__init__(**kwargs)
        log.debug("Scenario using async timers: %r.",
                  self._fsm_use_async_timers)

    def reset(self):
        """Reset the scenario to the initial state. No actions are called."""
        self.setState(InitialStateKey)
        dele = self.delegate
        if dele is not None and hasattr(dele, Scenario.DelegateResetMethod):
            getattr(dele, Scenario.DelegateResetMethod)()
