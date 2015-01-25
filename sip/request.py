import defaults
import _util
from header import Header


class Request(_util.ValueBinder):
    """Enumeration class generator"""

    types = _util.Enum(
        ("ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"),
        normalize=_util.upper)

    mandatoryheaders = (
        Header.types.From,  Header.types.To, Header.types.Via,
        Header.types.call_id, Header.types.cseq, Header.types.max_forwards)
    shouldheaders = ()  # Should be sent but parties must cope without.
    conditionalheaders = ()
    optionalheaders = (
        Header.types.authorization, Header.types.content_disposition,
        Header.types.content_encoding, Header.types.content_language,
        Header.types.content_type)
    streamheaders = (  # Required to be sent with stream-based protocols.
        Header.types.content_length,)
    bodyheaders = None  # Required with non-empty bodies.
    naheaders = None  # By default the complement of the union of the others.

    # This gives me case insensitive subclass instance creation and type-
    # checking.
    __metaclass__ = _util.attributesubclassgen

    def __str__(self):
        return "{type} {uri} {protocol}".format(**self.__dict__)

    def __init__(self, uri=None, protocol=defaults.sipprotocol):
        super(Request, self).__init__()
        for prop in ("uri", "protocol"):
            setattr(self, prop, locals()[prop])
        self.type = self.type


class InviteRequest(Request):
    type = Request.types.invite
