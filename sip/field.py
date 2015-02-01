"""Complex fields in SIP messages.
"""
import _util
import vb
import defaults
import param
import pdb


class Field(vb.ValueBinder):

    # For headers that delegate properties, these are the properties to
    # delegate. To be overridden in subclasses.
    delegateattributes = ["parameters"]

    def __init__(self, value=None, parms=None):
        super(Field, self).__init__()
        self.parameters = param.Parameters()
        if value is not None:
            self.value = value

    def __str__(self):
        rs = "{self.value}".format(**locals())
        rslist = [rs] + [str(val) for val in self.parameters.itervalues()]
        rs = ";".join(rslist)
        return rs

    def __setattr__(self, attr, val):
        if attr in param.Param.types:
            return setattr(self.parameters, attr, val)
        super(Field, self).__setattr__(attr, val)


class ViaField(Field):

    delegateattributes = (
        Field.delegateattributes + ["protocol", "transport", "host"])

    def __init__(self, host=None, protocol=defaults.sipprotocol,
                 transport=defaults.transport, parms=[]):
        super(ViaField, self).__init__(parms=parms)
        self.protocol = protocol
        self.transport = transport
        self.host = None

    @property
    def value(self):

        prottrans = "/".join((self.protocol, self.transport))
        if self.host is None:
            rv = prottrans
        else:
            rv = "{prottrans} {self.host}".format(**locals())

        return rv
