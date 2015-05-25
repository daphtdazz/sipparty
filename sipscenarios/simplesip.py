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
            tks.NewState: "invite sent",
            tks.Action: "sendInvite"
        },
        "invite": {
            tks.NewState: "in call",
            tks.Action: "reply200"
        }
    },
    "invite sent": {
        4: {
            tks.NewState: isk
        },
        200: {
            tks.NewState: "in call"
        }
    },
    "in call": {
        "send bye": {
            tks.NewState: "bye sent"
        },
        "bye": {
            tks.NewState: isk
        }
    },
    "bye sent": {
        200: {
            tks.NewState: isk
        }
    }
}


class SimpleParty(sip.Party):
    ScenarioDefinitions = Simple
