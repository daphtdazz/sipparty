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
import param

KeyHeaders = "headers"

KeyActAdd = "add"
KeyActRemove = "remove"
KeyActCopy = "copy"

default = {
    "INVITE": {
        200: {
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
    }
}
