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


class BindingException(Exception):
    """Base class for all binding specific errors."""


class NoSuchBinding(BindingException):
    """No such binding error: raised when we attempt to """


class BindingAlreadyExists(BindingException):
    """This binding already exists."""


class ValueBinder(object):
    """This mixin class provides a way to bind values to one another."""

    PathSeparator = "."
    PS = PathSeparator

    KeyTargetPath = "targetpath"
    KeyTransformer = "transformer"
    KeyDirections = "bothdirections"  # Only present on the root binding.

    def bind(self, frompath, topath, transformer=None, bothways=False):
        """Bind one attribute path to another, and optionally bind back the
        other way too.
        E.g.
        self.bind("a.b", "c")
        Means bind "a.b" to "c", such that if "a.b" changes, set "c" to be
        "a.b". To implement this, add the binding "a.b" to "c" to our
        dictionary and recurse down the "frompath", using:
        self._onewaybind("a.b", "c")

        If bothways is set, do the opposite too and mark in the binding that we
        did:
        self._onewaybind("c", "a.b")
        """
        self._bindoneway(frompath, topath, None, transformer)
        if bothways:
            fromattr, _, fromattrattrs = frompath.partition(ValueBinder.PS)
            attrbindings = self._bindings[fromattr]
            bindingdict = attrbindings[fromattrattrs]
            bindingdict[ValueBinder.KeyDirections] = True
            assert transformer is None
            self._bindoneway(topath, frompath, None, None)

    def unbind(self, frompath):
        """Unbind an attribute path."""

        # May need to unbind in the other direction.
        fromattr, _, fromattrattrs = frompath.partition(ValueBinder.PS)
        if fromattr not in self._bindings:
            raise(NoSuchBinding(frompath))

        attrbindings = self._bindings[fromattr]
        if fromattrattrs not in attrbindings:
            raise(NoSuchBinding(frompath))

        bindingdict = attrbindings[fromattrattrs]
        bothways = (ValueBinder.KeyDirections in bindingdict and
                    bindingdict[ValueBinder.KeyDirections])
        if bothways:
            topath = bindingdict[ValueBinder.KeyTargetPath]
            self._unbindoneway(topath)

        self._unbindoneway(frompath)

    def __setattr__(self, attr, val):

        # Protect against recursion. This might occur when one property of
        # ourself is bound to another.
        if (hasattr(self, "_bindings") and attr in self._bindings and
                not self._settingattr):
            self._settingattr = True
            try:
                attrbindings = self._bindings[attr]
                for path, bindingdict in attrbindings.iteritems():
                    # Handle directly bound attributes.
                    if len(path) == 0:
                        # This attribute is bound directly.
                        # print("Direct bound attribute changing: {attr}."
                        #      "{path}".format(**locals()))
                        target, targetattr = self._resolveboundobjectandattr(
                            bindingdict[ValueBinder.KeyTargetPath])
                        if target is not None:
                            # TODO: implement transformers.
                            tf = bindingdict[ValueBinder.KeyTransformer]
                            if tf:
                                tval = tf(val)
                            else:
                                tval = val

                            setattr(target, targetattr, tval)
                        continue

                    # Handle indirectly bound attributes.
                    else:
                        if hasattr(self, attr):
                            # print("Remove old binding: {attr}."
                            #       "{path}".format(**locals()))
                            getattr(self, attr).unbind(path)

                        if val is not None:
                            # print("Add new binding.")
                            val._bindoneway(
                                path,
                                (ValueBinder.PS +
                                 bindingdict[ValueBinder.KeyTargetPath]),
                                self,
                                bindingdict[ValueBinder.KeyTransformer])
            except:
                raise
            finally:
                self._settingattr = False

        super(ValueBinder, self).__setattr__(attr, val)

    def _bindoneway(self, frompath, topath, parent, transformer):
        """Binds the attribute at frompath to the attribute at topath, so a
        change to frompath causes a change to topath, but not vice-versa.
        E.g.
        self._bindoneway("a.b", "c")
        Adds an entry in the binding dictionary for "a.b" to "c", then if we
        have an attribute "a", recurses, binding "a"'s "b" to its parent (us)'s
        "c":
        self.a._bindoneway("b", ".c")
        """
        self._ensurevbness()

        attr, _, attrsattr = frompath.partition(ValueBinder.PS)
        if attr not in self._bindings:
            self._bindings[attr] = {}

        attrbindings = self._bindings[attr]

        # The attribute path of the attribute we're trying to bind should not
        # already be bound.
        if attrsattr in attrbindings:
            raise(BindingAlreadyExists(frompath))

        attrbindings[attrsattr] = {
            ValueBinder.KeyTargetPath: topath,
            ValueBinder.KeyTransformer: transformer}

        currparent = self._bindingparent
        assert currparent is None or currparent is parent
        self._bindingparent = parent

        if attrsattr and hasattr(self, attr):
            child = getattr(self, attr)
            child._bindoneway(attrsattr, ValueBinder.PS + topath, self,
                              transformer)

        print("Bindings after onewaybind: {self._bindings}".format(
            **locals()))

    def _ensurevbness(self):
        for reqdattr in (("_bindings", {}), ("_bindingparent", None),
                         ("_settingattr", False)):
            if not reqdattr[0] in self.__dict__:
                self.__dict__[reqdattr[0]] = reqdattr[1]

    def _unbindoneway(self, frompath):

        fromattr, _, fromattrattrs = frompath.partition(ValueBinder.PS)
        if fromattr not in self._bindings:
            raise(NoSuchBinding(frompath))

        bindings = self._bindings[fromattr]
        if fromattrattrs not in bindings:
            raise(NoSuchBinding(frompath))

        bindingdict = bindings[fromattrattrs]

        if len(fromattrattrs) and hasattr(self, fromattr):
            getattr(self, fromattr)._unbindoneway(fromattrattrs)

        del bindings[fromattrattrs]
        if not len(bindings):
            del self._bindings[fromattr]

        if not len(self._bindings):
            self._bindingparent = None

        print("Bindings after onewayUNbind: {self._bindings}".format(
            **locals()))

    def _resolveboundobjectandattr(self, path):
        nextobj = self
        splitpath = path.split(ValueBinder.PS)
        for nextattr in splitpath[0:-1]:
            # print("Next attribute: {nextattr}".format(**locals()))

            if len(nextattr) == 0:
                nextattr = "_bindingparent"

            if not hasattr(nextobj, nextattr):
                # This we're missing an object in the path, so need to return
                # None.
                nextobj = None
                nextattr = None
                break

            nextobj = getattr(nextobj, nextattr)

        else:
            nextattr = splitpath[-1]
        return nextobj, nextattr
