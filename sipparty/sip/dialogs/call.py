"""call.py

Standard dialog definitions (call, register etc.).

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
from ...util import Enum
from ...fsm import (InitialStateKey as InitialState, TransitionKeys)
from ..dialog import Dialog
from ..header import ContactHeader
from ..param import Param
from ..transform import TransformKeys


# States, Actions and Inputs.
S = Enum((
    InitialState, "InitiatingDialog", "InDialog", "TerminatingDialog", "Error",
    "Terminated"))
A = Enum((
    "sendRequestINVITE", "sendResponse200", "errorResponse", "sendRequestBYE",
    "hasTerminated"))
I = Enum((
    "initiate", "receiveRequestINVITE", "receiveResponse18",
    "receiveResponse2", "receiveResponse4", "terminate", "receiveRequestBYE"))

for transitionKey in TransitionKeys:
    locals()[transitionKey] = transitionKey
tsk = TransitionKeys
tfk = TransformKeys


class SimpleCall(Dialog):

    FSMDefinitions = {
        S.Initial: {
            I.initiate: {
                tsk.NewState: S.InitiatingDialog,
                tsk.Action: A.sendRequestINVITE
            },
            I.receiveRequestINVITE: {
                tsk.NewState: S.InDialog,
                tsk.Action: A.sendResponse200
            }
        },
        S.InitiatingDialog: {
            I.receiveResponse18: {
                tsk.NewState: S.InitiatingDialog
            },
            I.receiveResponse2: {
                tsk.NewState: S.InDialog
            },
            I.receiveResponse4: {
                tsk.NewState: S.Error,
                tsk.Action: A.errorResponse
            }
        },
        S.InDialog: {
            I.receiveResponse2: {
                tsk.NewState: S.InDialog
            },
            I.terminate: {
                tsk.NewState: S.TerminatingDialog,
                tsk.Action: A.sendRequestBYE
            },
            I.receiveRequestBYE: {
                tsk.NewState: S.Terminated,
                tsk.Action: A.sendResponse200,
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
