#!/usr/bin/env python
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
import sipparty
from sipparty.sip.components import URI
from sipparty.parse import ParseError
from sipparty.sip.siptransport import prot_log
from sipparty.parties import SingleRTPSessionSimplenParty

log = logging.getLogger()
logging.basicConfig()
log.setLevel(logging.INFO)


class SipCallArgs(argparse.ArgumentParser):
    "Argument parser for the script."

    def __init__(self):
        super(SipCallArgs, self).__init__(
            usage="%(prog)s <uri> [options]")

        self.add_argument("uri")
        self.add_argument(
            '--debug', '-D', type=int, nargs='?', help='Turn on debugging',
            default=logging.WARNING)

        self.args = self.parse_args()

        if self.args.debug is None:
            self.args.debug = logging.DEBUG

        try:
            self.args.uri = URI.Parse(self.args.uri)
        except ParseError:
            self.error("%r is not a valid URI." % (self.args.uri,))

#
# =================== Main script. =======================================
#
args = SipCallArgs().args

prot_log.setLevel(logging.ERROR)
if args.debug < logging.INFO:
    prot_log.setLevel(logging.INFO)
    log.setLevel(args.debug)
    sipparty.util.log.setLevel(logging.INFO)
    sipparty.fsm.retrythread.log.setLevel(logging.INFO)

pt = SingleRTPSessionSimplenParty("sip:simple-call@domain.com")
pt.listen()

dlg = pt.invite(args.uri)
log.info("Call beginning...")

dlg.waitForStateCondition(
    lambda state: state not in (
        dlg.States.Initial, dlg.States.SentInvite))  # noqa

pause_secs = 30
log.info("Call up, wait for %r seconds, or Ctrl-C", pause_secs)
try:
    time.sleep(pause_secs)
except KeyboardInterrupt:
    log.info("Ctrl-C causing us to continue.")

dlg.hit(dlg.Inputs.terminate)
log.info("Call terminating...")

dlg.waitForStateCondition(
    lambda state: state in (dlg.States.Terminated, dlg.States.Error))  # noqa

log.info("Finished.")

# Deleting the party and dialogue speeds up termination time, as we don't need
# to leave it to the python runtime to determine these references are no longer
# in use. This is because there are background threads running that will wait
# for these objects to be destroyed before terminating.
del pt
del dlg
