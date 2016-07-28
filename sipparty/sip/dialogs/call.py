"""Standard dialog definitions (call, register etc.).

Copyright 2015 David Park.

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

from ...fsm import (InitialStateKey as InitialState, TransitionKeys)
from ...util import Enum
from ..dialog import Dialog
from ..header import ContactHeader
from ..param import Param
from ..transform import TransformKeys

log = logging.getLogger(__name__)

# States, Actions and Inputs.
S = Enum((
    InitialState, 'ReceivedInvite', "SentInvite", "InDialog",
    "TerminatingDialog", "Error",
    "Terminated"))
I = Enum((
    "initiate", 'accept', 'reject', "receiveRequestINVITE",
    "receiveResponse18",
    "receiveResponse2", "receiveResponse4", "terminate", "receiveRequestBYE"))

for transitionKey in TransitionKeys:
    locals()[transitionKey] = transitionKey
tsk = TransitionKeys
tfk = TransformKeys


class SimpleCallDialog(Dialog):

    FSMDefinitions = {
        S.Initial: {
            I.initiate: {
                tsk.NewState: S.SentInvite,
                tsk.Action: ['session_listen', ('send_request', 'INVITE')]
            },
            I.receiveRequestINVITE: {
                tsk.NewState: S.ReceivedInvite,
                tsk.Action: 'handle_invite',
            }
        },
        S.ReceivedInvite: {
            I.accept: {
                tsk.NewState: S.InDialog,
                tsk.Action: (('send_response', 200),),
            },
            I.reject: {
                tsk.NewState: S.Terminated,
                tsk.Action: 'send_response',
            }
        },
        S.SentInvite: {
            I.receiveResponse18: {
                tsk.NewState: S.SentInvite
            },
            I.receiveResponse2: {
                tsk.NewState: S.InDialog,
                tsk.Action: 'send_ack'
            },
            I.receiveResponse4: {
                tsk.NewState: S.Error,
                tsk.Action: 'errorResponse'
            }
        },
        S.InDialog: {
            I.receiveResponse2: {
                tsk.NewState: S.InDialog
            },
            I.terminate: {
                tsk.NewState: S.TerminatingDialog,
                tsk.Action: (('send_request', 'BYE'),)
            },
            I.receiveRequestBYE: {
                tsk.NewState: S.Terminated,
                tsk.Action: (('send_response', 200),)
            }
        },
        S.TerminatingDialog: {
            I.receiveResponse2: {
                tsk.NewState: S.Terminated
            }
        },
        S.Error: {},
        S.Terminated: {}
    }

    Transforms = {
        "INVITE": {
            2: [
                (tfk.Copy, "FromHeader",),
                (tfk.Copy, "ToHeader",),
                (tfk.Copy, "ViaHeader",),
                (tfk.Copy, "Call_IdHeader",),
                (tfk.Copy, "CseqHeader",),
                (tfk.Copy, "startline.protocol",),
                (tfk.Add, "ToHeader.field.parameters.tag",
                 lambda _: Param.tag()),
                (tfk.Add, 'ContactHeader', lambda _: ContactHeader())
            ]
        },
        "BYE": {
            2: [
                (tfk.Copy, "FromHeader",),
                (tfk.Copy, "ToHeader",),
                (tfk.Copy, "ViaHeader",),
                (tfk.Copy, "Call_IdHeader",),
                (tfk.Copy, "CseqHeader",),
                (tfk.Copy, "startline.protocol",),
                (tfk.Add, 'ContactHeader', lambda _: ContactHeader())
            ]
        },
    }

    def fsm_dele_handle_invite(self, *args, **kwargs):
        log.debug('default delegate handling invite')
        self.hit(self.Inputs.accept, *args, **kwargs)
