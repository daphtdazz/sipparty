import defaults
import components
import _util
import vb
from header import Header


class Request(vb.ValueBinder):
    """Enumeration class generator"""

    types = _util.Enum(
        ("ACK", "BYE", "CANCEL", "INVITE", "OPTIONS", "REGISTER"),
        normalize=_util.upper)

    # This gives me case insensitive subclass instance creation and type-
    # checking.
    __metaclass__ = _util.attributesubclassgen

    type = _util.ClassType("Request")

    def __str__(self):
        return "{self.type} {self.uri} {self.protocol}".format(self=self)

    def __init__(self, uri=None, protocol=defaults.sipprotocol):
        super(Request, self).__init__()
        if uri is None:
            uri = components.URI()

        for prop in ("uri", "protocol"):
            setattr(self, prop, locals()[prop])
