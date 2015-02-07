"""vb.py

Copyright David Park 2015
"""
import logging

log = logging.getLogger(__name__)
log.level = logging.ERROR


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

    def __init__(self, *args, **kwargs):

        for reqdattr in (
                ("_vb_forwardbindings", {}), ("_vb_backwardbindings", {}),
                ("_vb_bindingparent", None)):
            # Have to set this on dict to avoid recursing, as __setattr__
            # requires these to have already been set.  Also means we need to
            # do this before calling super, in case super sets any attrs.
            self.__dict__[reqdattr[0]] = reqdattr[1]

        super(ValueBinder, self).__init__(*args, **kwargs)

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

    def unbind(self, frompath):
        """Unbind a binding."""
        _, _, _, _, bdict = self._vb_bindingdicts(frompath, "forward")
        topath = bdict[self.KeyTargetPath]
        self._vb_unbinddirection(frompath, "forward")
        self._vb_unbinddirection(topath, "backward")

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
                        topath = bdict[ValueBinder.KeyTargetPath]
                        if val is not existing_val:
                            log.debug(
                                "Push %s.%s to %s", attr, fromattrattrs,
                                topath)
                            self._vb_push_value_to_target(val, topath)
                    continue

                # This is an indirect binding, so need to update the first
                # item's binding.
                if existing_val is not None:
                    existing_val._vb_unbinddirection(fromattrattrs, direction)

                if val is not None:
                    val._vb_binddirection(
                        fromattrattrs,
                        ValueBinder.PS + bdict[ValueBinder.KeyTargetPath],
                        self,
                        bdict[ValueBinder.KeyTransformer],
                        direction)

        try:
            super(ValueBinder, self).__setattr__(attr, val)
        except AttributeError as exc:
            raise AttributeError(
                "Can't set {attr!r} on {self.__class__.__name__!r} instance: "
                "{exc}".format(**locals()))

    def _vb_bindingsForDirection(self, direction):
        try:
            return getattr(self, "_vb_%sbindings" % direction)
        except AttributeError as exc:
            raise AttributeError(
                str(exc) +
                "\nAre you sure you called super().__init__() for this class?")

    def _vb_bindingActionForDirection(self, direction):
        try:
            return getattr(self, "_vb_bind%s" % direction)
        except AttributeError as exc:
            raise AttributeError(
                str(exc) +
                "\nAre you sure you called super().__init__() for this class?")

    def _vb_bindingdicts(self, path, direction, create=False, all=False):
        bindings = self._vb_bindingsForDirection(direction)

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
                raise(BindingAlreadyExists(
                    "{0!r} is in {2!r} binding dict {1!r}".format(
                        path, bindings, direction)))
            attrdict[attrattrs] = {}

        if attrattrs not in attrdict:
            if not all:
                raise(NoSuchBinding(path))
            return bindings, attr, attrattrs, attrdict, None

        return bindings, attr, attrattrs, attrdict, attrdict[attrattrs]

    def _vb_push_value_to_target(self, value, topath):
        target, toattr = self._vb_resolveboundobjectandattr(topath)
        if target is not None:
            log.debug("Pushing %r to %s", value, topath)
            setattr(target, toattr, value)
        else:
            log.debug("Target not available to push %s", topath)

    def _vb_pull_value_to_self(self, myattr, topath):
        target, toattr = self._vb_resolveboundobjectandattr(topath)
        if target is not None and hasattr(target, toattr):
            val = getattr(target, toattr)
            setattr(self, myattr, val)

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
                subobj = getattr(self, fromattr)
                if not hasattr(subobj, "_vb_bindforward"):
                    raise TypeError(
                        "Attribute {fromattr!r} of "
                        "{self.__class__.__name__!r} does not support "
                        "bindings. It "
                        "has type {subobj.__class__.__name__!r}."
                        "".format(**locals()))
                subobj._vb_bindforward(
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
                val = getattr(self, fromattr)
                if val is not None:
                    val._vb_bindbackward(
                        fromattrattrs, ValueBinder.PS + topath, self,
                        transformer)
        else:
            # Direct binding. See if we can pull the value.
            self._vb_pull_value_to_self(fromattr, topath)

    def _vb_unbinddirection(self, frompath, direction):
        bindings, fromattr, fromattrattrs, attrbindings, _ = (
            self._vb_bindingdicts(frompath, direction, create=False))

        if len(fromattrattrs) > 0 and hasattr(self, fromattr):
            getattr(self, fromattr)._vb_unbinddirection(fromattrattrs,
                                                        direction)

        del attrbindings[fromattrattrs]
        if len(attrbindings) == 0:
            del bindings[fromattr]

    def _vb_resolveboundobjectandattr(self, path):
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
