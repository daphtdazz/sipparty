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
from sipparty.sip.dialog import Dialog

# States, Actions and Inputs.
S = util.Enum((
    InitialState, "InitiatingDialog", "InDialog", "TerminatingDialog", "Error",
    "Terminated"))
A = util.Enum((
    "sendRequestInvite", "sendResponse200", "errorResponse", "sendRequestBye"))
I = util.Enum((
    "initiate", "receiveRequestInvite", "receiveResponse18",
    "receiveResponse2", "receiveResponse4", "terminate", "receiveRequestBye"))

for transitionKey in fsm.TransitionKeys:
    locals()[transitionKey] = transitionKey

class SimpleCall(Dialog):

    FSMDefinitions = {
        S.Initial: {
            I.initiate: {
                NewState: S.InitiatingDialog,
                Action: A.sendRequestInvite
            },
            I.receiveRequestInvite: {
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
                Action: A.sendRequestBye
            },
            I.receiveRequestBye: {
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
