""":Copyright: David Park 2015

Implements the `Party` object.
"""
import defaults

__all__ = ('Party',)


class Party(object):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    def __init__(self):
        """
        """
        self.port = defaults.port

    def listen(self):
        """
        """

    # Send methods.
    def register(self):
        """Register the party with a server."""

    def invite(self):
        """Start a call."""

    def sendResponse(self, code, toParty=None):
        """Send a SIP response code."""

    # Receiving methods.
    def receive_response(self, code):
        """Receive a response code after a request."""
