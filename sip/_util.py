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

    @classmethod
    def BindingDictNameForDirection(cls, direction):
        return "_vb_%sbindings" % direction

    def _vb_bindingActionForDirection(self, direction):
        return getattr(self, "_vb_bind%s" % direction)

    def __init__(self, *args, **kwargs):

        for reqdattr in (
                ("_vb_forwardbindings", {}), ("_vb_backwardbindings", {}),
                ("_vb_bindingparent", None)):
            # Have to set this on dict to avoid recursing, as __setattr__
            # requires these to have already been set.  Also means we need to
            # do this before calling super, in case super sets any attrs.
            self.__dict__[reqdattr[0]] = reqdattr[1]

        super(ValueBinder, self).__init__(*args, **kwargs)

    def _vb_bindingdicts(self, path, direction, create=False, all=False):
        dname = ValueBinder.BindingDictNameForDirection(direction)
        bindings = getattr(self, dname)

        attr, _, attrattrs = path.partition(ValueBinder.PS)
        if attr not in bindings:
            if not create:
                raise(NoSuchBinding(path))
            attrdict = {}
            bindings[attr] = attrdict
        else:
            attrdict = bindings[attr]

        # Resolve the attrdict.
        if create:
            if attrattrs in attrdict:
                raise(BindingAlreadyExists(path))
            attrdict[attrattrs] = {}

        if attrattrs not in attrdict:
            if not all:
                raise(NoSuchBinding(path))
            return bindings, attr, attrattrs, attrdict, None

        return bindings, attr, attrattrs, attrdict, attrdict[attrattrs]

    def _vb_push_value_to_target(self, value, topath):
        target, toattr = self._resolveboundobjectandattr(topath)
        if target is not None:
            setattr(target, toattr, value)

    def _vb_pull_value_to_self(self, myattr, topath):
        target, toattr = self._resolveboundobjectandattr(topath)
        if target is not None and hasattr(target, toattr):
            val = getattr(target, toattr)
            setattr(self, myattr, val)

    def bind(self, frompath, topath, transformer=None):
        """When any item on frompath or topath changes, set topath to frompath.
        E.g.
        self.a = a
        a = a
        a.b = b
        a.b.c = 6
        self.bind("a.b.c", "d.e")
        self.d = d
        >> self.d.e = 6
        del a.b
        g.c = 5
        a.b = g
        >> a.d.e = 5
        """
        self._vb_bindforward(frompath, topath, self, transformer)
        self._vb_bindbackward(topath, frompath, self, None)

    def _vb_binddirection(self, frompath, topath, parent, transformer,
                          direction):
        action = self._vb_bindingActionForDirection(direction)
        action(frompath, topath, parent, transformer)

    def _vb_bindforward(self, frompath, topath, parent, transformer):
        """Bind so any change in frompath causes topath to be updated from
        frompath (if possible).
        E.g.
        self._vb_bindforward("a.b", "c.d")
        self.a.b = 6
        """
        # Make the attribute binding dictionary if it doesn't already exist.
        _, fromattr, fromattrattrs, _, bdict = self._vb_bindingdicts(
            frompath, "forward", create=True)
        bdict[ValueBinder.KeyTargetPath] = topath
        bdict[ValueBinder.KeyTransformer] = transformer

        currparent = self._vb_bindingparent
        assert currparent is None or currparent is parent
        self._vb_bindingparent = parent

        if fromattrattrs:
            # This is an indirect binding, so recurse if possible.
            # E.g.
            # self.bindforward("a.b", "c")
            # >> self.a.bindforward("b", ".c")
            if hasattr(self, fromattr):
                getattr(self, fromattr)._vb_bindforward(
                    fromattrattrs, ValueBinder.PS + topath, self, transformer)
        else:
            # This is a direct binding. If we already have a value for it, set
            # the target. E.g.
            # self.bindforward("c", ".a")
            # >> self._vb_parent.a = self.c
            if hasattr(self, fromattr):
                val = getattr(self, fromattr)
                self._vb_push_value_to_target(val, topath)

    def _vb_bindbackward(self, frompath, topath, parent, transformer):
        """Bind so any change in frompath causes frompath to be updated from
        topath (if possible).
        E.g.

        """
        # Get the binding dictionary, creating it if doesn't exist.
        _, fromattr, fromattrattrs, _, bdict = self._vb_bindingdicts(
            frompath, "backward", create=True)
        bdict[ValueBinder.KeyTargetPath] = topath
        bdict[ValueBinder.KeyTransformer] = transformer

        currparent = self._vb_bindingparent
        assert currparent is None or currparent is parent
        self._vb_bindingparent = parent

        if fromattrattrs:
            # Indirect binding, so recurse if we have the attribute.
            # E.g.
            # self.bindbackward("a.b", ".c")
            # >> self.a.bindbackward("b", "..c")
            if hasattr(self, fromattr):
                getattr(self, fromattr)._vb_bindbackward(
                    fromattrattrs, ValueBinder.PS + topath, self, transformer)
        else:
            # Direct binding. See if we can pull the value.
            self._vb_pull_value_to_self(fromattr, topath)

    def unbind(self, frompath):
        """Unbind a binding, back and forward."""
        _, _, _, _, bdict = self._vb_bindingdicts(frompath, "forward")
        topath = bdict[self.KeyTargetPath]
        self._vb_unbinddirection(frompath, "forward")
        self._vb_unbinddirection(topath, "backward")

    def _vb_unbinddirection(self, frompath, direction):
        bindings, fromattr, fromattrattrs, attrbindings, _ = (
            self._vb_bindingdicts(frompath, direction, create=False))

        if len(fromattrattrs) > 0 and hasattr(self, fromattr):
            getattr(self, fromattr)._vb_unbinddirection(fromattrattrs,
                                                        direction)

        del attrbindings[fromattrattrs]
        if len(attrbindings) == 0:
            del bindings[fromattr]

    def __setattr__(self, attr, val):

        if hasattr(self, attr):
            existing_val = getattr(self, attr)
        else:
            existing_val = None

        for direction in ("forward", "backward"):
            try:
                _, _, _, bdicts, _ = self._vb_bindingdicts(attr, direction,
                                                           all=True)
            except NoSuchBinding:
                # This attribute is not bound in this direction.
                continue

            for fromattrattrs, bdict in bdicts.iteritems():
                if len(fromattrattrs) == 0:
                    # This is a direct binding.
                    #
                    # If this is backwards then there's nothing to do, because
                    # we are being overridden.
                    #
                    # If forward, then push the change to the target.
                    if direction == "forward":
                        # Push the change, only if it is a change to avoid
                        # recursion.
                        if val is not existing_val:
                            self._vb_push_value_to_target(
                                val, bdict[ValueBinder.KeyTargetPath])
                    continue

                # This is an indirect binding, so need to update the first
                # item's binding.
                if existing_val is not None:
                    existing_val._vb_unbinddirection(fromattrattrs, direction)

                val._vb_binddirection(
                    fromattrattrs,
                    ValueBinder.PS + bdict[ValueBinder.KeyTargetPath],
                    self,
                    bdict[ValueBinder.KeyTransformer],
                    direction)

        super(ValueBinder, self).__setattr__(attr, val)

    def _resolveboundobjectandattr(self, path):
        nextobj = self
        splitpath = path.split(ValueBinder.PS)
        for nextattr in splitpath[0:-1]:
            # print("Next attribute: {nextattr}".format(**locals()))

            if len(nextattr) == 0:
                nextattr = "_vb_bindingparent"

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
