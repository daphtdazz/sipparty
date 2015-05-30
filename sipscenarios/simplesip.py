"""simplesip.py

A very simple SIP scenario which provides the ability to make and receive a
phone call.

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
import sip

tks = sip.scenario.TransitionKeys
isk = sip.scenario.InitialStateKey

Simple = {
    isk: {
        "sendInvite": {
            tks.NewState: "InviteSent",
            tks.Action: "_sendInvite"
        },
        "invite": {
            tks.NewState: "InCall",
            tks.Action: "_reply200"
        }
    },
    "InviteSent": {
        4: {
            tks.NewState: isk
        },
        200: {
            tks.NewState: "InCall"
        }
    },
    "InCall": {
        "sendBye": {
            tks.NewState: "ByeSent",
            tks.Action: "_sendBye"
        },
        "bye": {
            tks.NewState: "CallEnded",
            tks.Action: "_reply200"
        }
    },
    "ByeSent": {
        200: {
            tks.NewState: "CallEnded"
        }
    },
    "CallEnded": {}
}


class SimpleParty(sip.Party):
    ScenarioDefinitions = Simple
