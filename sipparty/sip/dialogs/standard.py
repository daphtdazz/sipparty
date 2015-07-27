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
from ..dialog import (Dialog, Inputs, States)
#from dialog import Dialog
from sipparty import util, fsm
#from sip import Dialog

#tks = sip.scenario.TransitionKeys
#isk = sip.scenario.InitialStateKey
#NewState = sip.scenario.TransitionKeys.NewState
#Action = sip.scenario.TransitionKeys.Action

CallFSMDefn = {
    fsm.InitialStateKey: {
        Inputs.initiate: {
            fsm.TransitionKeys.NewState: States.InitiatingDialog,
            fsm.TransitionKeys.Action: "sendRequest"
            #fsm.TransitionKeys.Action: "sendRequestINVITE"
        }
    },
    States.InitiatingDialog: {

    },
    States.InDialog: {

    },
    States.TerminatingDialog: {

    },
    States.ErrorCompletion: {},
    States.SuccessCompletion: {}
}

CallDialog = type("CallDialog", (Dialog,), {"FSMDefinitions": CallFSMDefn})
