"""Defaults for SIP
"""
import prot
import components

__all__ = ("port", "sipprotocol", "scheme")

port = 5060
sipprotocol = "SIP/2.0"
transport = "UDP"
scheme = "sip"
max_forwards = 70

AORs = [
    components.AOR("alice", "atlanta.com"),
    components.AOR("bob", "biloxi.com"),
    components.AOR("charlotte", "charlesville.com"),
    components.AOR("darren", "denver.com")
]
