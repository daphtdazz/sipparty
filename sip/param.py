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

    types = _util.Enum(("branch", "tag",), normalize=lambda x: x.lower())

    __metaclass__ = _util.attributesubclassgen

    name = _util.ClassType("Param")

    def __init__(self, value=None):
        super(Param, self).__init__()
        self.values = []
        if value is not None:
            self.value = value

    def __str__(self):
        if not hasattr(self, "value") and hasattr(self, "newvalue"):
            self.value = self.newvalue()
        return "{self.name}={self.value}".format(self=self)


class BranchParam(Param):

    BranchNumber = random.randint(1, 10000)
    BranchMagicCookie = "z9hG4bK"

    def __init__(self, startline=None, branch_num=None):
        super(BranchParam, self).__init__()
        self.startline = startline
        if branch_num is None:
            branch_num = BranchParam.BranchNumber
            BranchParam.BranchNumber += 1
        self.branch_num = branch_num

    @property
    def value(self):
        str_to_hash = "{0}-{1}".format(str(self.startline), self.branch_num)
        the_hash = hash(str_to_hash)
        if the_hash < 0:
            the_hash = - the_hash
        return "{0}{1:x}".format(BranchParam.BranchMagicCookie, the_hash)


class TagParam(Param):

    def __init__(self, tagtype=None):
        # tagtype could be used to help ensure that the From: and To: tags are
        # different all the time.
        super(TagParam, self).__init__()
        self.tagtype = tagtype

    def newvalue(self):
        # RFC 3261 asks for 32 bits of randomness. Expect random is good
        # enough.
        return "{0:04x}".format(random.randint(0, 2**32 - 1))
