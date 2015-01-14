"""Utility functions for py-sip.
"""


class attributetomethodgenerator(type):
    """Metaclass that catches unknown class attributes and calls a class method
    to generate an object for them."""
    def __getattr__(cls, name):
        return cls.generateobjectfromname(name)


class attributesubclassgen(type):

    def __init__(cls, name, bases, dict):
        cls._supername = name

    def __getattr__(cls, name):
        if "types" not in cls.__dict__:
            raise AttributeError(
                "{cls.__name__!r} needs a 'types' attribute.".format(
                    **locals()))

        if name not in cls.__dict__["types"]:
            raise AttributeError(
                "{name!r} is not a valid subtype of {cls.__name__!r}".format(
                    **locals()))
        print "get " + name
        name = getattr(cls.__dict__["types"], name)
        print "normalized to " + name
        subclassguess = name.title() + cls._supername

        try:
            mod = __import__(cls.__module__)
            for modname in cls.__module__.split(".")[1:]:
                mod = getattr(mod, modname)
            rclass = getattr(mod, subclassguess)
            rclass.type = name
            return rclass

        except AttributeError:
            return type(subclassguess, (cls,), dict(type=name))


def upper(key):
    """A normalizer for Enum, which uppercases the key."""
    return key.upper()


def title(key):
    """A normalizer for Enum, which titles the key (So-Like-This)."""
    return key.title()


def sipheader(key):
    """Normalizer for SIP headers, which is almost title but not quite."""
    nk = key.title()
    nk = nk.replace("_", "-")
    if nk == "Call-Id":
        nk = "Call-ID"
    elif nk == "Www-Authenticate":
        nk = "WWW-Authenticate"
    elif nk == "Cseq":
        nk = "CSeq"
    elif nk == "Mime-Version":
        nk = "MIME-Version"

    return nk


class Enum(set):
    """Thank you http://stackoverflow.com/questions/36932/
    how-can-i-represent-an-enum-in-python"""

    def __init__(self, vals, normalize=None):
        self.normalize = normalize
        super(self.__class__, self).__init__(vals)

    def __contains__(self, val):
        if self.normalize:
            nn = self.normalize(val)
        else:
            nn = val
        return super(Enum, self).__contains__(nn)

    def __getattr__(self, name):
        if self.normalize:
            nn = self.normalize(name)
        else:
            nn = name
        if nn in self:
            return nn
        raise AttributeError(nn)
