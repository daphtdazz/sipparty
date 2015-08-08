"""standard.py

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
from sipparty import util, fsm
from sipparty.fsm import InitialStateKey as InitialState
from sipparty.sip.dialog import Dialog, TransformKeys
from sipparty.sip.param import Param

# States, Actions and Inputs.
S = util.Enum((
    InitialState, "InitiatingDialog", "InDialog", "TerminatingDialog", "Error",
    "Terminated"))
A = util.Enum((
    "sendRequestINVITE", "sendResponse200", "errorResponse", "sendRequestBYE"))
I = util.Enum((
    "initiate", "receiveRequestINVITE", "receiveResponse18",
    "receiveResponse2", "receiveResponse4", "terminate", "receiveRequestBYE"))

for transitionKey in fsm.TransitionKeys:
    locals()[transitionKey] = transitionKey
for transformKey in TransformKeys:
    locals()[transformKey] = transformKey

class SimpleCall(Dialog):

    FSMDefinitions = {
        S.Initial: {
            I.initiate: {
                NewState: S.InitiatingDialog,
                Action: A.sendRequestINVITE
            },
            I.receiveRequestINVITE: {
                NewState: S.InDialog,
                Action: A.sendResponse200
            }
        },
        S.InitiatingDialog: {
            I.receiveResponse18: {
                NewState: S.InitiatingDialog
            },
            I.receiveResponse2: {
                NewState: S.InDialog,
            },
            I.receiveResponse4: {
                NewState: S.Error,
                Action: A.errorResponse
            }
        },
        S.InDialog: {
            I.terminate: {
                NewState: S.TerminatingDialog,
                Action: A.sendRequestBYE
            },
            I.receiveRequestBYE: {
                NewState: S.Terminated,
                Action: A.sendResponse200
            }
        },
        S.TerminatingDialog: {
            I.receiveResponse2: {
                NewState: S.Terminated
            }
        },
        S.Error: {},
        S.Terminated: {}
    }

    Transforms = {
        "INVITE": {
            2: [
                (Copy, "FromHeader",),
                (Copy, "ToHeader",),
                (Copy, "ViaHeader",),
                (Copy, "Call_IdHeader",),
                (Copy, "CseqHeader",),
                (Copy, "startline.protocol",),
                (Add, "ToHeader.field.parameters.tag", lambda _: Param.tag())
            ]
        },
        "BYE": {
            2: [
                (Copy, "FromHeader",),
                (Copy, "ToHeader",),
                (Copy, "ViaHeader",),
                (Copy, "Call_IdHeader",),
                (Copy, "CseqHeader",),
                (Copy, "startline.protocol",)
            ]
        },
        2: {
            "ACK": [
                (Copy, "startline.protocol",),
                (Copy, "FromHeader",),
                (Copy, "ToHeader",),
                (Copy, "ViaHeader",),
                (CopyFromRequest, "startline.uri",)
            ]
        }
    }
