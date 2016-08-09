"""test_standard_calls.py

Unit tests for a SIP party.

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
# from gc import collect as gc_collect
import logging
# from weakref import ref
from .setup import SIPPartyTestCase
# from ..fsm import UnexpectedInput
# from ..sip.components import (AOR, Host, URI)
from ..sip.dialogs import SimpleServerDialog
from ..parties import NoMediaSimpleCallsParty

from ..util import WaitFor

log = logging.getLogger(__name__)


class TestDialogDelegate:

    def __init__(self):
        self.invite_count = 0

    def fsm_dele_handle_invite(self, *args, **kwargs):
        self.invite_count += 1


class TestStandardDialog(SIPPartyTestCase):

    def test_basic(self):

        dd = TestDialogDelegate()

        p1, p2 = [
            NoMediaSimpleCallsParty(dialog_delegate=dd) for ii in range(2)]

        p1.display_name_uri = 'sip:alice@atlanta.com'
        p2.display_name_uri = 'sip:bob@biloxi.com'

        p2.listen(port=0)

        p1.invite(p2)
        WaitFor(lambda: dd.invite_count == 1)
