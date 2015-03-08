"""vb.py

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import logging
import re

log = logging.getLogger(__name__)
log.level = logging.DEBUG


class BindingException(Exception):
    """Base class for all binding specific errors."""


class NoSuchBinding(BindingException):
    """No such binding error: raised when we attempt to unbind a binding
    that doesn't exist."""


class BindingAlreadyExists(BindingException):
    """This binding already exists: raised when attempting to bind an
    attribute that is already bound."""


class ValueBinder(object):
    """This mixin class provides a way to bind values to one another."""

    PathSeparator = "."
    PS = PathSeparator

    KeyTargetPath = "targetpath"
    KeyTransformer = "transformer"

    VB_Forward = 'forward'
    VB_Backward = 'backward'
    VB_Directions = (VB_Forward, VB_Backward)

    def __init__(self, *args, **kwargs):

        for reqdattr in (
                ("_vb_forwardbindings", {}), ("_vb_backwardbindings", {}),
                ("_vb_bindingparent", None),
                ("_vb_leader_res", None),
                ("_vb_followers", None),
                ("_vb_delegate_attributes", {})):
            # Have to set this on dict to avoid recursing, as __setattr__
            # requires these to have already been set.  Also means we need to
            # do this before calling super, in case super sets any attrs.
            self.__dict__[reqdattr[0]] = reqdattr[1]

        super(ValueBinder, self).__init__(*args, **kwargs)

        if hasattr(self, "vb_dependencies"):
            log.debug("%r has VB dependencies", self.__class__.__name__)
            deps = self.vb_dependencies
            deleattrmap = self._vb_delegate_attributes
            for dele, deleattrs in deps:
                for deleattr in deleattrs:
                    if deleattr in deleattrmap:
                        raise ValueError(
                            "Delegate attribute %r declared twice" % deleattr)
                    log.debug("Attr %r is delegated through %r", deleattr,
                              dele)
                    deleattrmap[deleattr] = dele

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
        log.debug("Bind %r to %r", frompath, topath)
        self._vb_binddirection(
            frompath, topath, self, transformer, self.VB_Forward)
        self._vb_binddirection(
            topath, frompath, self, transformer, self.VB_Backward)

    def unbind(self, frompath):
        """Unbind a binding. Raises NoSuchBinding() if the binding does not
        exist."""
        log.debug("Unbind %r", frompath)
        _, _, _, _, bdict = self._vb_bindingdicts(frompath, self.VB_Forward)
        topath = bdict[self.KeyTargetPath]
        self._vb_unbinddirection(frompath, self.VB_Forward)
        self._vb_unbinddirection(topath, self.VB_Backward)

    def __getattr__(self, attr):
        """If the attribute is a delegated attribute, gets the attribute from
        the delegate, else calls super."""
        if attr in self._vb_delegate_attributes:
            return getattr(getattr(self, self._vb_delegate_attributes[attr]),
                           attr)

        if hasattr(super(ValueBinder, self), "__getattr__"):
            return super(ValueBinder, self).__getattr__(attr)

        raise AttributeError("%r instance has no attribute %r" %
                             (self.__class__, attr))

    def __setattr__(self, attr, val):
        """
        Call super (so we don't do the rest if super fails).

        Unbind existing value.

        Bind to attr if in a binding path.

        Propagate bindings.
        """

        log.debug("Setattr %r", attr)

        if attr not in set(("_vb_bindingparent", )) and hasattr(self, attr):
            existing_val = getattr(self, attr)
        else:
            existing_val = None

        try:
            super(ValueBinder, self).__setattr__(attr, val)
        except AttributeError as exc:
            raise AttributeError(
                "Can't set {attr!r} on {self.__class__.__name__!r} instance: "
                "{exc}".format(**locals()))

        # If this is a delegated attribute, pass through.
        if attr in self._vb_delegate_attributes:
            deleattr = getattr(self, self._vb_delegate_attributes[attr])
            log.debug("Passthrough delegate attr %r to %r", attr, deleattr)
            return setattr(deleattr, attr, val)

        if hasattr(existing_val, "_vb_unbindAllParent"):
            existing_val._vb_unbindAllParent()

        if hasattr(val, "_vb_binddirection"):
            for direction in self.VB_Directions:
                _, _, _, bs, _ = self._vb_bindingdicts(attr, direction,
                                                       all=True)
                for subpath, bdict in bs.iteritems():
                    if len(subpath) == 0:
                        continue
                    topath = bdict[self.KeyTargetPath]
                    subtopath = self.VB_PrependParent(topath)
                    tf = bdict[self.KeyTransformer]
                    log.debug("%r bind new value %r to %r", direction,
                              subpath, subtopath)
                    val._vb_binddirection(subpath, subtopath, self, tf,
                                          direction)

        # If this attribute is forward bound, push the value out.
        _, _, _, fbds, _ = self._vb_bindingdicts(attr, self.VB_Forward,
                                                 all=True)

        for fromattrattrs, bdict in fbds.iteritems():
            if len(fromattrattrs) == 0:
                topath = bdict[ValueBinder.KeyTargetPath]
                log.debug("Push %s.%s to %s", attr, fromattrattrs,
                          topath)
                self._vb_push_value_to_target(val, topath)

    @classmethod
    def VB_SplitPath(cls, path):
        return path.split(cls.PS)

    @classmethod
    def VB_PartitionPath(cls, path):
        first, sep, rest = path.partition(cls.PS)
        return first, rest

    @classmethod
    def VB_JoinPath(cls, path):
        return cls.PS.join(path)

    @classmethod
    def VB_PrependParent(cls, path):
        lp = [path]
        lp.insert(0, '')
        return cls.VB_JoinPath(lp)

    def _vb_unbindAllParent(self):
        for direction in self.VB_Directions:
            abds = self._vb_bindingsForDirection(direction)
            log.debug("unbind any parent bindings in %d %r bindings (%r)",
                      len(abds), direction, abds)
            for attr in dict(abds):
                _, _, _, bs, _ = self._vb_bindingdicts(
                    attr, direction, all=True)
                log.debug("  %d bindings through %r", len(bs), attr)
                for subpath, bdict in dict(bs).iteritems():
                    topath = bdict[self.KeyTargetPath]
                    toattr, _ = self.VB_PartitionPath(topath)
                    log.debug("  binding %r %r -> %r", attr, subpath,
                              toattr)
                    if len(toattr) == 0:
                        log.debug("Unbind parent binding.")
                        path = self.VB_JoinPath((attr, subpath))
                        self._vb_unbinddirection(path, direction)

    def _vb_resolveFromPath(self, path):
        """Returns the actual binding path, rather than one that might be
        through a dependency.

        So if a.c resolves to a.b.c, then:
        a._vb_resolveFromPath("c")
        >>> "b.c"
        """
        attr, _ = self.VB_PartitionPath(path)
        if attr not in self._vb_delegate_attributes:
            return path

        return self.VB_JoinPath((self._vb_delegate_attributes[attr], path))

    def _vb_bindingsForDirection(self, direction):
        try:
            return getattr(self, "_vb_%sbindings" % direction)
        except AttributeError as exc:
            raise AttributeError(
                str(exc) +
                " Are you sure you called super().__init__() for this class?")

    def _vb_bindingdicts(self, path, direction, create=False, all=False):
        """Returns the binding information for a path and direction, if there
        is any. If there isn't raises NoSuchBinding() unless create is
        specified.

        bindings, attr, attrattrs, attrdict, topath = self._vb_bindingdicts(
            path, direction)

        bindings - the dictionary of bindings for the direction, keyed by
        attribute.
        attr - the first item of path: key into bindings.
        attrattrs - the remainder of path, the subpath that is bound: key into
        attrdict
        attrdict - dictionary of all the subpaths of attr that are bound.
        Keyed by subpath (of which attrattrs is one if not "all" requested).
        topath - the binding dictionary (keys are KeyTargetPath and
        KeyTransformer). None if the binding doesn't exist, empty dictionary
        if create was specified and the binding didn't previously exist.

        create - create a binding dictionary for the path if it doesn't
        already exist
        """
        bindings = self._vb_bindingsForDirection(direction)
        attr, attrattrs = self.VB_PartitionPath(path)

        if attr not in bindings:
            if not create:
                if all:
                    return bindings, attr, attrattrs, {}, None
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

        if all:
            return bindings, attr, attrattrs, attrdict, None

        if attrattrs not in attrdict:
            raise NoSuchBinding(path)

        return bindings, attr, attrattrs, attrdict, attrdict[attrattrs]

    def _vb_push_value_to_target(self, value, topath):
        log.debug("Push value to %r", topath)
        target, toattr = self._vb_resolveboundobjectandattr(topath)
        if target is not None:
            if hasattr(target, toattr):
                old_value = getattr(target, toattr)
            else:
                old_value = None
            if value is not old_value:
                log.debug("Pushing %r to %s", value, topath)
                setattr(target, toattr, value)
            else:
                log.debug("Target's value already is value!")
        else:
            log.debug("Target not available to push %s", topath)

    def _vb_pull_value_to_self(self, myattr, topath):
        log.debug("Pull value from %r", topath)
        target, toattr = self._vb_resolveboundobjectandattr(topath)
        if target is not None and hasattr(target, toattr):
            val = getattr(target, toattr)
            setattr(self, myattr, val)

    def _vb_binddirection(self, frompath, topath, parent, transformer,
                          direction):
        """
        """
        log.debug("  %r bindings before bind %r",
                  direction,
                  self._vb_bindingsForDirection(self.VB_Forward))
        resolvedpath = self._vb_resolveFromPath(frompath)

        # Make the attribute binding dictionary if it doesn't already exist.
        _, fromattr, fromattrattrs, _, bdict = self._vb_bindingdicts(
            resolvedpath, direction, create=True)
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
            log.debug("indirect %r binding %r -> %r", direction, frompath,
                      topath)
            if hasattr(self, fromattr):
                log.debug("  has child at %r.", fromattr)
                subobj = getattr(self, fromattr)
                if hasattr(subobj, "_vb_binddirection"):
                    log.debug("  child is VB compatible.")
                    subobj._vb_binddirection(
                        fromattrattrs, ValueBinder.PS + topath, self,
                        transformer, direction)
        else:
            # This is a direct binding. If we already have a value for it, set
            # the target. E.g.
            # self.bindforward("c", ".a")
            # >> self._vb_parent.a = self.c
            log.debug("direct %r binding %r -> %r", direction, frompath,
                      topath)
            if direction == self.VB_Forward:
                if hasattr(self, fromattr):
                    log.debug("  Has child attr %r", fromattr)
                    val = getattr(self, fromattr)
                    self._vb_push_value_to_target(val, topath)
            else:
                log.debug("Pull value.")
                self._vb_pull_value_to_self(fromattr, topath)

        log.debug("  %r bindings after bind %r",
                  direction,
                  self._vb_bindingsForDirection(self.VB_Forward))

    def _vb_unbinddirection(self, frompath, direction):
        """Unbind a particular path.

        Say "c.d" is bound forward to ".e.f" on b (the parent of b is a).

        b._vb_unbinddirection("c.d", VB_Forward)

        would undo this, and recurse to do:
        b.c._vb_unbinddirection("d", VB_Forward)
        """
        resolvedpath = self._vb_resolveFromPath(frompath)

        bindings, fromattr, fromattrattrs, attrbindings, _ = (
            self._vb_bindingdicts(resolvedpath, direction, create=False))

        if len(fromattrattrs) > 0 and hasattr(self, fromattr):
            getattr(self, fromattr)._vb_unbinddirection(fromattrattrs,
                                                        direction)

        del attrbindings[fromattrattrs]
        if len(attrbindings) == 0:
            del bindings[fromattr]

    def _vb_resolveboundobjectandattr(self, path):
        log.debug("resolve path %r", path)
        nextobj = self
        splitpath = self.VB_SplitPath(path)
        for nextattr in splitpath[0:-1]:

            if len(nextattr) == 0:
                nextattr = "_vb_bindingparent"

            log.debug("  try next attribute %r", nextattr)
            if not hasattr(nextobj, nextattr):
                # This we're missing an object in the path, so need to return
                # None.
                log.debug("  missing")
                nextobj = None
                nextattr = None
                break

            nextobj = getattr(nextobj, nextattr)

        else:
            nextattr = splitpath[-1]
        return nextobj, nextattr
