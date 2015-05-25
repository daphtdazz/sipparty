"""default.py

Defaults for SIP

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
import prot
import components

__all__ = ("port", "sipprotocol", "scheme")

port = 5060
sipprotocol = "SIP/2.0"
transport = "UDP"
scheme = "sip"
max_forwards = 70

AORs = [
    components.AOR(username=un, host=ho)
    for un, ho in (
        ("alice", "atlanta.com"),
        ("bob", "biloxi.com"),
        ("charlotte", "charlesville.com"),
        ("darren", "denver.com"))
]
