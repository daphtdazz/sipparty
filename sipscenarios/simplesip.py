#!/usr/bin/python
"""
"""
import logging
logging.basicConfig()
log = logging.getLogger()

import sip

tks = sip.scenario.TransitionKeys


class Simple(sip.Party):

    ScenarioDefinitions = {
        sip.scenario.InitialStateKey: {
            "invite": {
                tks.NewState: "invited"
            }
        },
        "invite sent": {

        }
    }

if __name__ == '__main__':
    sc = Simple()
