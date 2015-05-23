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
    log.setLevel(logging.DEBUG)

TransitionKeys = copy.copy(fsm.TransitionKeys)
tks = TransitionKeys  # Short alias
InitialStateKey = fsm.InitialStateKey


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

        super(Scenario, cls).PopulateWithDefinition(definition_dict)

    actionCallback = _util.DerivedProperty("_scn_actionCallback")

    def __init__(self, transform=None, transitions=None, **kwargs):
        self._scn_actionCallback = None
        super(Scenario, self).__init__(**kwargs)
        log.debug("Scenario using async timers: %r.",
                  self._fsm_use_async_timers)

    def __getattr__(self, attr):
        log.debug("scenario getattr %r", attr)

        if attr.startswith("_scn_action"):

            message = attr.replace("_scn_action", "", 1)

            try:
                scn_action = _util.WeakMethod(
                    self, "_scn_action", static_args=[message],
                    default_rc=None)
            except:
                log.exception("")
                raise
            log.debug("Return scn_action")
            return scn_action

        if not hasattr(super(Scenario, self), attr):
            raise AttributeError(
                "{self.__class__!r} instance has no attribute {attr!r}."
                "".format(**locals()))

    def _scn_action(self, message, *args, **kwargs):
        log.debug("Scenario action for message %r.", message)
        cbk = self.actionCallback
        if cbk is not None:
            cbk(message, *args, **kwargs)
