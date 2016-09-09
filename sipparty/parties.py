"""parties.py

Implements various convenient `Party` subclasses.

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
from __future__ import absolute_import

from six import itervalues
from .sip.dialogs import SimpleClientDialog, SimpleServerDialog
from .media.sessions import SingleRTPSession
from .party import Party


class NoMediaSimpleCallsParty(Party):
    """A Party with no media session

    Useful for testing that the signaling works.
    """

    MediaSession = None
    ClientDialog = SimpleClientDialog
    ServerDialog = SimpleServerDialog


class SingleRTPSessionSimplenParty(Party):
    ClientDialog = SimpleClientDialog
    ServerDialog = SimpleServerDialog
    MediaSession = SingleRTPSession

AllPartyTypes = [
    _lval for _lval in itervalues(dict(locals()))
    if isinstance(_lval, type)
    if issubclass(_lval, Party)
    if _lval is not Party
]
