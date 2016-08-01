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
from ..standardtimers import StandardTimers
from ..transform import TransformKeys

log = logging.getLogger(__name__)

for transitionKey in TransitionKeys:
    locals()[transitionKey] = transitionKey
tsk = TransitionKeys
tfk = TransformKeys


class SimpleClientDialog(Dialog):

    Inputs = Enum((
        "initiate",
        "response_18",
        "response_2", 'response_xxx',
        "terminate", "receiveRequestBYE"))
    I = Inputs

    States = Enum((
        InitialState, "SentInvite", "InDialog",
        "TerminatingDialog",
        "Terminated"))
    S = States

    FSMDefinitions = {
        S.Initial: {
            I.initiate: {
                tsk.NewState: S.SentInvite,
                tsk.Action: ['session_listen', ('send_request', 'INVITE')]
            },
        },
        S.SentInvite: {
            I.response_18: {
                tsk.NewState: S.SentInvite
            },
            I.response_2: {
                tsk.NewState: S.InDialog,
                tsk.Action: 'send_ack'
            },
            I.response_xxx: {
                tsk.NewState: S.Terminated,
                tsk.Action: 'errorResponse'
            }
        },
        S.InDialog: {
            I.response_2: {
                tsk.Action: 'send_ack',
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
            I.response_2: {
                tsk.Action: 'send_ack',
            },
            I.response_2: {
                tsk.NewState: S.Terminated
            }
        },
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


class SimpleServerDialog(Dialog):

    Inputs = Enum((
        "initiate", 'accept', 'reject',
        "receiveRequestINVITE", 'receiveRequestACK', "receiveRequestBYE",
        "response_2",
        "terminate", ))
    I = Inputs

    States = Enum((
        InitialState, 'ReceivedInvite', 'Sent200', "InDialog",
        "TerminatingDialog",
        "Terminated"))
    S = States

    FSMTimers = {
        '200_retry': (
            'resend_response',
            StandardTimers.names.standard_timer_retransmit_gen),
        '200_retry_giveup': (
            [('hit', Inputs.terminate)],
            StandardTimers.names.standard_timer_giveup_gen),
    }

    FSMDefinitions = {
        S.Initial: {
            I.receiveRequestINVITE: {
                tsk.NewState: S.ReceivedInvite,
                tsk.Action: 'handle_invite',
                # TODO: 13.3.1 says if the INVITE contains an expires header
                # we should start a timer after which we'll send 487 if accept
                # hasn't generated another input.
                # tsk.StartTimers
            }
        },
        S.ReceivedInvite: {
            I.accept: {
                tsk.NewState: S.Sent200,
                tsk.Action: (('send_response', 200),),
                tsk.StartTimers: ('200_retry', '200_retry_giveup'),
            },
            I.reject: {
                tsk.NewState: S.Terminated,
                tsk.Action: [('send_response', 487)],
            }
        },
        S.Sent200: {
            I.receiveRequestACK: {
                tsk.NewState: S.InDialog,
                tsk.StopTimers: ('200_retry', '200_retry_giveup'),
            },
            I.terminate: {
                tsk.NewState: S.TerminatingDialog,
                tsk.Action: (('send_request', 'BYE'),),
                tsk.StopTimers: ('200_retry', '200_retry_giveup'),
            },
        },
        S.InDialog: {
            I.terminate: {
                tsk.NewState: S.TerminatingDialog,
                tsk.Action: (('send_request', 'BYE'),)
            },
            I.receiveRequestBYE: {
                tsk.NewState: S.Terminated,
                tsk.Action: (('send_response', 200),)
            },
        },
        S.TerminatingDialog: {
            I.response_2: {
                tsk.NewState: S.Terminated
            }
        },
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
