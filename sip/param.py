import random
import _util
import vb


class Param(vb.ValueBinder):

    types = _util.Enum(("branch",), normalize=lambda x: x.lower())

    def __init__(self, name, value):
        self.name = name
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
        super(BranchParam, self).__init__(self.types.branch)
