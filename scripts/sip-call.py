#!/usr/bin/python
"""sip-call.py

An example script that makes a phone call for illustration and basic testing
purposes.

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
import argparse
import logging
import time
import socket

import sipparty
from sipparty import sipscenarios

log = logging.getLogger()
logging.basicConfig()
log.setLevel(logging.INFO)


class SipCallArgs(argparse.ArgumentParser):
    "Argument parser for the script."

    def __init__(self):
        super(SipCallArgs, self).__init__(
            usage="%(prog)s <aor> [options]")

        self.add_argument("aor")
        self.add_argument(
            '--debug', '-D', type=int, nargs='?', help='Turn on debugging',
            default=logging.WARNING)

        self.args = self.parse_args()

        if self.args.debug is None:
            self.args.debug = logging.DEBUG


#
# =================== Main script. =======================================
#
args = SipCallArgs().args

sipparty.sip.transport.prot_log.setLevel(logging.INFO)
if args.debug < logging.INFO:
    sipparty.util.log.setLevel(logging.INFO)
    sipparty.fsm.retrythread.log.setLevel(logging.INFO)


sipclient = sipscenarios.SimpleParty(socketType=socket.SOCK_DGRAM)

sipclient.sendInvite(args.aor)
sipclient.waitUntilState(sipclient.States.InCall,
                         error_state=sipclient.States.Initial,
                         timeout=5)

log.info("Finished.")
