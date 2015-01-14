""":Copyright: David Park 2015

Implements the `Party` object.
"""
import defaults
import prot

__all__ = ('Party',)


class Party(object):
    """A party in a sip call, aka an endpoint, caller or callee etc.
    """

    def __init__(self, username=None, host=None, displayname=None):
        """
        """

        self.port = defaults.port
        self.sentmessages = []
        self.rcvdmessages = []
        self.AOR = prot.URL("user", "localhost")

    def listen(self):
        """
        """

    # Send methods.
    def register(self):
        """Register the party with a server."""

    def invite(self, ):
        """Start a call."""
        invite = prot.Message.invite

    def sendResponse(self, code, toParty=None):
        """Send a SIP response code."""

    # Receiving methods.
    def receive_response(self, code):
        """Receive a response code after a request."""
