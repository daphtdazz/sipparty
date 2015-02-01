import random
import _util
import vb


class Parameters(vb.ValueBinder, dict):

    def __init__(self):
        super(Parameters, self).__init__()
        self.parms = {}

    def __setattr__(self, attr, val):
        super(Parameters, self).__setattr__(attr, val)
        if attr in Param.types:
            self[attr] = val


class Param(vb.ValueBinder):

    types = _util.Enum(("branch",), normalize=lambda x: x.lower())

    __metaclass__ = _util.attributesubclassgen

    name = _util.ClassType("Param")
    value = _util.Value()

    def __init__(self, value=None):
        super(Param, self).__init__()
        self.values = []
        if value is not None:
            self.value = value

    def __str__(self):
        return "{self.name}={self.value}".format(self=self)


def RequestToBranchTransformer(request):

    str_to_has = "{0}-{1}".format(str(request), BranchParam.BranchNumber)
    BranchParam.BranchNumber += 1
    the_hash = hash(str_to_has)
    if the_hash < 0:
        the_hash = - the_hash
    return "{0}{1:x}".format(BranchParam.BranchMagicCookie, the_hash)


class BranchParam(Param):

    BranchNumber = random.randint(1, 10000)
    BranchMagicCookie = "z9hG4bK"

    def __init__(self):
        super(BranchParam, self).__init__()
        self.startline = None

    @property
    def value(self):
        if len(self.values) > 0:
            return self.values[0]

        if self.startline is not None:
            return RequestToBranchTransformer(self.startline)
        return ""

    @value.setter
    def value(self, val):
        self.values.insert(0, val)
