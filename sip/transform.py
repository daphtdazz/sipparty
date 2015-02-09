"""transform.py

Contains transformations for SIP messages.

Copyright David Park 2015
"""
import param

KeyHeaders = "headers"

KeyActAdd = "add"
KeyActRemove = "remove"
KeyActCopy = "copy"

request = {
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
                ("ToHeader.value.parameters.tag", param.Param.tag)
            ]
        }
    }
}
