"""Utility functions for py-sip.
"""
import pdb


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


class ValueBinder(object):
    """This mixin class provides a way to bind values to one another."""

    PathSeparator = "."
    PS = PathSeparator

    KeyTargetPath = "targetpath"
    KeyTransformer = "transformer"

    def __init__(self, *args, **kwargs):
        for reqdattr in (("_bindings", {}), ("_bindingparent", None),
                         ("_settingattr", False)):
            if not reqdattr[0] in self.__dict__:
                self.__dict__[reqdattr[0]] = reqdattr[1]
        super(ValueBinder, self).__init__(*args, **kwargs)

    def bind(self, frompath, topath, transformer=None):
        """E.g. vb.bind("a.b", "..c") would bind my attribute a's attribute b
        to my parent's parent's attribute c."""

        # print("Bindings before bind: {self._bindings}".format(**locals()))

        # Bind from to to.
        self._bindoneway(frompath, topath, transformer)

        # If the first element of topath is not empty, then this means we are
        # the bottom object in the binding path, so we need to bind up to the
        # topath too.  This should generally be the case.  Any other situation
        # and we wouldn't have enough information to bind the reverse direction
        # because it would involving attempting to find a child that we don't
        # know the name of.  E.g. we can bind 'a.b' to '.c' (i.e. our parent's
        # 'c' attribute, but we can't bind the parent's 'c' to our 'a.b'
        # because we don't know our name in the parent's attribute dictionary,
        # so can't work out the full path for the parent: '<us??>.a.b'

        toattr, _, toattrsattr = topath.partition(ValueBinder.PS)
        if toattr:
            self._bindoneway(topath, frompath, transformer)

        # print("Bindings before bind: {self._bindings}".format(**locals()))

    def unbind(self, frompath):
        """Unbind an attribute path."""

        # print("Bindings before unbind({frompath}): {self._bindings}".format(
        #    **locals()))

        # May need to unbind in the other direction.
        fromattr, _, fromattrattrs = frompath.partition(ValueBinder.PS)
        assert fromattr in self._bindings

        bindings = self._bindings[fromattr]
        assert fromattrattrs in bindings
        bindingdict = bindings[fromattrattrs]

        topath = bindingdict[ValueBinder.KeyTargetPath]
        toattr, _, toattrattrs = frompath.partition(ValueBinder.PS)
        if len(toattr) and hasattr(self, toattr):
            # To attr not the parent and we have it, so unbind it.
            self._unbindoneway(topath)

        self._unbindoneway(frompath)

        # print("Bindings after unbind: {self._bindings}".format(**locals()))

    def __setattr__(self, attr, val):
        # print("VB setattr({attr}: {val})".format(**locals()))

        # Protect against recursion. This might occur when one property of
        # ourself is bound to another.
        if attr != "_settingattr" and not self._settingattr:
            self._settingattr = True
            try:
                if attr in self._bindings:
                    attrbindings = self._bindings[attr]
                    for path, bindingdict in attrbindings.iteritems():
                        # Handle directly bound attributes.
                        if len(path) == 0:
                            # This attribute is bound directly.
                            target, targetattr = (
                                self._resolveboundobjectandattr(
                                    bindingdict[ValueBinder.KeyTargetPath]))
                            if target is not None:
                                # TODO: implement transformers.
                                setattr(target, targetattr, val)
                            continue
                        # Handle indirectly bound attributes.

            except:
                raise
            finally:
                self._settingattr = False

        super(ValueBinder, self).__setattr__(attr, val)

    def _bindoneway(self, frompath, topath, transformer):
        """Binds the attribute at frompath to the attribute at topath, so a
        change to frompath causes a change to topath, but not vice-versa."""

        attr, _, attrsattr = frompath.partition(ValueBinder.PS)
        if attr not in self._bindings:
            self._bindings[attr] = {}

        attrbindings = self._bindings[attr]

        # The attribute path of the attribute we're trying to bind should not
        # already be bound.
        assert attrsattr not in attrbindings
        attrbindings[attrsattr] = {
            ValueBinder.KeyTargetPath: topath,
            ValueBinder.KeyTransformer: transformer}

        if attrsattr and hasattr(self, attr):
            child = getattr(self, attr)
            child._bindingparent = self
            child.bind(attrsattr, ValueBinder.PS + topath)

    def _unbindoneway(self, frompath):
        fromattr, _, fromattrattrs = frompath.partition(ValueBinder.PS)
        assert fromattr in self._bindings

        bindings = self._bindings[fromattr]
        assert fromattrattrs in bindings
        bindingdict = bindings[fromattrattrs]

        if len(fromattrattrs) and hasattr(self, fromattr):
            getattr(self, fromattr)._unbindoneway(fromattrattrs)

        del bindings[fromattrattrs]

    def _resolveboundobjectandattr(self, path):
        nextobj = self
        splitpath = path.split(ValueBinder.PS)
        nextattr = splitpath[0]
        for nextattr in splitpath[:-1]:
            if len(nextattr) == 0:
                nextattr = "_bindingparent"
            if hasattr(nextobj, nextattr):
                nextobj = getattr(nextobj, nextattr)
                continue

            return None, ""

        return nextobj, nextattr
