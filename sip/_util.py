"""Utility functions for py-sip.
"""
import logging
import pdb
import vb

log = logging.getLogger(__name__)


class attributetomethodgenerator(type):
    """Metaclass that catches unknown class attributes and calls a class method
    to generate an object for them."""
    def __getattr__(cls, name):
        return cls.generateobjectfromname(name)


class attributesubclassgen(type):
    """This is used as a metaclass to give automatic subclass creation from
    attribute access.

    So for example:

    class AttributeGen(object):

        types = Enum(("Subclass",))
        __metaclass__ = attributesubclassgen

    class SubclassAttributeGen(object):
        pass

    inst = AttributeGen.Subclass()

    >>> inst is an instance of Subclass.
    """

    def __init__(cls, name, bases, dict):
        """__init__ for classes is called after the bases and dict have been
        set up, so no need to re-set up here."""
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

        name = getattr(cls.__dict__["types"], name)
        subclassguess = name.title().replace("-", "_") + cls._supername
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


class ClassType(object):

    def __init__(self, class_append):
        self.class_append = class_append

    def __get__(self, instance, owner):
        if instance is None:
            return ""

        class_name = instance.__class__.__name__
        return getattr(instance.types, class_name.replace(
            self.class_append, ""))


class Value(object):
    def __get__(self, instance, owner):
        if instance is None or len(instance.values) == 0:
            raise AttributeError(
                "{0!r} does not have attribute 'value'".format(owner.__name__))

        return instance.values[0]

    def __set__(self, instance, val):
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute 'value'".format(owner.__name__))

        instance.values.insert(0, val)


class GenerateIfNotSet(object):
    def __init__(self, attrname, alwaysregen=False):
        self.attrname = attrname
        self._gins_generator_name = "generate_%s" % attrname
        self._gins_always_regen = alwaysregen

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute {1!r}".format(
                    owner.__name__, self.attrname))

        if (self._gins_always_regen or
                self.attrname not in instance.__dict__ or
                instance.__dict__[self.attrname] is None):
            if not hasattr(instance, self._gins_generator_name):
                raise AttributeError(
                    "{instance.__class__.__name__!r} instance wants to "
                    "generate attribute {self.attrname!r} but has no "
                    "generator method {self._gins_generator_name!r}")

            instance.__dict__[self.attrname] = getattr(
                instance, self._gins_generator_name)()

        return instance.__dict__[self.attrname]

    def __set__(self, instance, value):
        instance.__dict__[self.attrname] = value

    def __delete__(self, instance):
        del instance.__dict__[self.attrname]


class Resets(object):
    """This descriptor, when set, causes the attributes in resetattrs on the
    instance to be deleted."""
    def __init__(self, attr, resetattrs):
        self.attr = attr
        self._resets_attrs = resetattrs

    def __get__(self, instance, owner):
        if instance is None:
            raise AttributeError(
                "{0!r} does not have attribute {1!r}".format(
                    owner.__name__, self.attr))

        if self.attr not in instance.__dict__:
            raise AttributeError(
                "{instance.__class__.__name__!r} has no attribute "
                "{self.attr!r}")

        return instance.__dict__[self.attr]

    def __set__(self, instance, value):
        instance.__dict__[self.attr] = value
        for resetattr in self.resetattrs:
            if hasattr(instance, resetattr):
                delattr(instance, resetattr)

    def __delete__(self, instance):
        del instance.__dict__[self.attr]


def CCPropsFor(props):

    class CumulativeClassProperties(type):
        def __new__(cls, name, bases, dict):
            """Initializes the class dictionary, so that all the properties in
            props are accumulated with all the inherited properties in the
            base classes.
            """
            log.debug("Accumulate properties %r of %r.", props, name)
            for cprop_name in props:
                if cprop_name not in dict:
                    log.debug("Class doesn't have property %r", cprop_name)
                    continue

                log.debug("Fixing %r", cprop_name)
                cprops = dict[cprop_name]
                log.debug("Starting properties %r", cprops)
                cpropstype = type(cprops)
                newcprops = cpropstype()
                for method_name in ("extend", "update"):
                    if hasattr(newcprops, method_name):
                        break
                else:
                    raise AttributeError(
                        "Cumulative property {cprop_name!r} is neither "
                        "extendable nor updatable."
                        "".format(**locals()))
                method = getattr(newcprops, method_name)
                blist = list(bases)
                log.debug("Base list: %r", blist)
                blist.reverse()
                for base in blist:
                    if hasattr(base, cprop_name):
                        inh_cprops = getattr(base, cprop_name)
                        method(inh_cprops)

                # Finally update with this class's version.
                method(cprops)
                dict[cprop_name] = newcprops
                log.debug("Ending properties %r", dict[cprop_name])

            return super(CumulativeClassProperties, cls).__new__(
                cls, name, bases, dict)

    return CumulativeClassProperties
