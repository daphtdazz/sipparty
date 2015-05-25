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
logging.basicConfig()

import sipscenarios

log = logging.getLogger()
log.setLevel(logging.DEBUG)


class SipCallArgs(argparse.ArgumentParser):
    "Argument parser for the script."

    def __init__(self):
        super(SipCallArgs, self).__init__(
            usage="%(prog)s <aor> [options]")

        self.add_argument("aor")
        self.add_argument(
            '--debug', '-D', type=int, nargs='?', help='Turn on debugging')

#
# =================== Main script. =======================================
#
args = SipCallArgs().parse_args()

sipclient = sipscenarios.SimpleParty()

sipclient.hit("sendInvite", args.aor)

log.info("Finished.")
