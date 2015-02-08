"""transform.py

Contains transformations for SIP messages.

Copyright David Park 2015
"""

KeyHeaders = "headers"

KeyActAdd = "add"
KeyActRemove = "remove"
KeyActCopy = "copy"

request = {
    "INVITE": {
        200: {
            KeyActCopy: [
                ("FromHeader",),
                ("ViaHeader",),
                ("Call_IdHeader",),
                ("CseqHeader",),
                ("startline.protocol",)
            ]
        }
    }
}
