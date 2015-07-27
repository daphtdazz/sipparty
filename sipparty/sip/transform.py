"""transform.py

Contains transformations for SIP messages.

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
from six import binary_type as bytes
from numbers import Integral
import param

KeyHeaders = "headers"

KeyActAdd = "add"
KeyActRemove = "remove"
KeyActCopy = "copy"
KeyActCopyFromRequest = "copy_from_original"

default = {
    "INVITE": {
        2: {
            KeyActCopy: [
                ("FromHeader",),
                ("ToHeader",),
                ("ViaHeader",),
                ("Call_IdHeader",),
                ("CseqHeader",),
                ("startline.protocol",)
            ],
            KeyActAdd: [
                ("ToHeader.field.parameters.tag", param.Param.tag)
            ]
        }
    },
    "BYE": {
        2: {
            KeyActCopy: [
                ("FromHeader",),
                ("ToHeader",),
                ("ViaHeader",),
                ("Call_IdHeader",),
                ("CseqHeader",),
                ("startline.protocol",)
            ]
        }
    },
    2: {
        "ACK": [
            {
                KeyActCopy: [
                    ("startline.protocol",),
                    ("FromHeader",),
                    ("ToHeader",),
                    ("ViaHeader",),
                ]
            },
            {
                KeyActCopyFromRequest: [
                    ("startline.uri",),
                ]
            }
        ]
    }
}

def EntryForMessageType(entry_dict, mtype):
    """
    Attempts to look up the mtype in the dictionary, and return the entry. If
    the mtype is a response code and it is not in the dictionary, attempts to
    find a more generic entry by dividing by ten and trying again.

    E.g: mtype = 401 but there is no 401 entry, and there is a 4 entry, then
    the 4 entry will be returned.

    :param mtype: The request or response type.
    :type mtype: String or integer.
    :return: The dictionary for the code or a parent.
    :raises IndexError: If no dictionary can be found for the code."""

    while isinstance(mtype, Integral) and mtype >= 1:
        if mtype in entry_dict:
            return entry_dict[mtype]

        mtype = mtype / 100

    return entry_dict[mtype]

