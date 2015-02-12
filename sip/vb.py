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

    def __init__(self, *args, **kwargs):

        for reqdattr in (
                ("_vb_forwardbindings", {}), ("_vb_backwardbindings", {}),
                ("_vb_bindingparent", None), ("_vb_proxies", {})):
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
        self._vb_binddirection(frompath, topath, self, transformer, 'forward')
        self._vb_binddirection(topath, frompath, self, transformer,
                               'backward')

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

    @classmethod
    def _ProxyRE(cls):
        if not hasattr(cls, "_vb_proxy_re"):
            cls._vb_proxy_re = re.compile(cls.vb_proxy_pattern)
        return cls._vb_proxy_re

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
        # Make the attribute binding dictionary if it doesn't already exist.
        _, fromattr, fromattrattrs, _, bdict = self._vb_bindingdicts(
            frompath, direction, create=True)
        bdict[ValueBinder.KeyTargetPath] = topath
        bdict[ValueBinder.KeyTransformer] = transformer

        currparent = self._vb_bindingparent
        assert currparent is None or currparent is parent
        self._vb_bindingparent = parent

        # At this point, if the fromattr is matches, delegate to the proxy.
        if hasattr(self, "vb_proxy_pattern"):
            # !!! DMP: need to get rid of the proxy object, not helping.
            # Instead just need to maintain a dictionary of attributes that
            # affect different attributes.
            regex = self._ProxyRE()
            if regex.match(fromattr):
                log.debug(
                    "%r instance proxy attribute %r being bound %s.",
                    self.__class__.__name__, fromattr, direction)
                if fromattr not in self._vb_proxies:
                    self._vb_proxies[fromattr] = VBProxy(self)
                return self._vb_proxies[fromattr]._vb_binddirection(
                    frompath, topath, parent, transformer, direction)

        if fromattrattrs:
            # This is an indirect binding, so recurse if possible.
            # E.g.
            # self.bindforward("a.b", "c")
            # >> self.a.bindforward("b", ".c")
            if hasattr(self, fromattr):
                subobj = getattr(self, fromattr)
                if subobj is not None:
                    subobj._vb_binddirection(
                        fromattrattrs, ValueBinder.PS + topath, self,
                        transformer, direction)
        else:
            # This is a direct binding. If we already have a value for it, set
            # the target. E.g.
            # self.bindforward("c", ".a")
            # >> self._vb_parent.a = self.c
            if direction == 'forward':
                if hasattr(self, fromattr):
                    val = getattr(self, fromattr)
                    self._vb_push_value_to_target(val, topath)
            else:
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


class VBProxy(ValueBinder):

    def __init__(self, owner):
        super(VBProxy, self).__init__()
        self._vbp_owner = owner





