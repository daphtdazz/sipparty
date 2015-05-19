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
import weakref
import collections

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
        new_dict = dict(definition_dict)

        # Normalize message names in the dictionary and add action based on
        # message.
        for state, stdict in six.iteritems(new_dict):
            for name, val in six.iteritems(dict(stdict)):
                if name in request.Request.types:
                    nn = getattr(request.Request.types, name)
                    stdict[nn] = val
                    del stdict[name]
                if tks.Message in val and tks.Action not in val:
                    message = val[tks.Message]
                    log.debug("Converting message %r into action.", message)
                    val[tks.Action] = (
                        "_scn_action" + six.binary_type(message))

        super(Scenario, cls).PopulateWithDefinition(definition_dict)

    state = _util.DerivedProperty(get="_scn_state")

    def __init__(self, transform=None, transitions=None):
        super(Scenario, self).__init__()
        pass

    def receiveMessage(self, msg):
        pass

    def __getattr__(self, attr):
        # if attr in
        if attr.startswith("_scn_action"):
            message = attr.replace("_scn_action", "", 1)
            wself = weakref.ref(self)

            def scn_action(*args, **kwargs):
                ss = wself()
                ss._scn_action(message, *args, **kwargs)

            log.debug("Returning func which %s a callable.",
                      "is" if isinstance(scn_action, collections.Callable)
                      else "is not")
            return scn_action

        if not hasattr(super(Scenario, self), attr):
            raise AttributeError(
                "{self.__class__!r} instance has no attribute {attr!r}."
                "".format(**locals()))

    def _scn_action(self, message, *args, **kwargs):
        log.debug("Scenario action for message %r.", message)
