"""scenario.py



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
import _util
import fsm
import request

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    log = logging.getLogger()
else:
    log = logging.getLogger(__name__)


TransitionKeys = copy.copy(fsm.TransitionKeys)
TransitionKeys.update(_util.Enum((
    "Message",
    # TODO: Action
    )))
tks = TransitionKeys  # Short alias
InitialStateKey = fsm.InitialStateKey
log.debug(tks)


def ScenarioClassWithDefinition(name, defn):
    nc = type(name + "Scenario", (Scenario,), {})
    nc.PopulateWithDefinition(defn)
    return nc


class Scenario(fsm.FSM):

    @classmethod
    def PopulateWithDefinition(cls, definition_dict):
        super(Scenario, cls).PopulateWithDefinition(definition_dict)

    def __init__(self, transform=None, transitions=None):
        pass

    def receiveMessage(self, msg):
        pass

    def __getattr__(self, attr):
        # if attr in

        if not hasattr(super(Scenario, self), attr):
            raise AttributeError(
                "{self.__class__!r} instance has no attribute {attr!r}."
                "".format(**locals()))
