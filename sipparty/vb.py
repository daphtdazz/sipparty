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
from six import (binary_type as bytes, iteritems)
from weakref import (ref as wref)

log = logging.getLogger(__name__)
log.setLevel(logging.WARNING)  # vb is verbose at lower levels.

KeyTransformer = "transformer"
KeyIgnoredExceptions = "ignore_exceptions"

# Use to generate extra profile info.
PROFILE = False

sentinel = type('ValueBinderNoAttributeSentinel', (), {})()


class BindingException(Exception):
    """Base class for all binding specific errors."""


class NoSuchBinding(BindingException):
    """No such binding error: raised when we attempt to unbind a binding
    that doesn't exist."""


class BindingAlreadyExists(BindingException):
    """This binding already exists: raised when attempting to bind an
    attribute that is already bound."""


class _VBSubClassMonitor(object):

    def __init__(self, subclass_counter_dict):
        self._vbsclsm_dict_attrname = subclass_counter_dict

    def __get__(self, instance, owner):

        adict = getattr(ValueBinder, self._vbsclsm_dict_attrname, None)
        if adict is None:
            adict = {}
            setattr(ValueBinder, self._vbsclsm_dict_attrname, adict)

        cn = owner.__name__

        def update_counter_dict(attrname=None):
            aname_dict = adict.get(cn, None)
            if aname_dict is None:
                if attrname is not None:
                    aname_dict = {}
                    adict[cn] = aname_dict
                else:
                    adict[cn] = 0

            if attrname is not None:
                curr_count = aname_dict.get(attrname, 0)
                aname_dict[attrname] = curr_count + 1
            else:
                adict[cn] += 1

        return update_counter_dict

    def __set__(self, instance, val):
        raise AttributeError(
            '\'_VBSubClassMonitor\' is not a writable property.')


class ValueBinder(object):
    """This mixin class provides a way to bind values to one another."""

    #
    # =================== CLASS INTERFACE ====================================
    #
    PathSeparator = "."
    PS = PathSeparator

    VB_Forward = 'forward'
    VB_Backward = 'backward'
    VB_Directions = (VB_Forward, VB_Backward)

    # Updated when PROFILE is true. Number of setattr calls for each subclass
    # of ValueBinder (keyed by class name).
    hit_set_attr = _VBSubClassMonitor('set_attr_calls')
    hit_init = _VBSubClassMonitor('init_calls')

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

    #
    # =================== INSTANCE INTERFACE =================================
    #
    def __init__(self, **kwargs):
        log.detail(
            'Initialize new VaueBinder properties for %r instance',
            self.__class__.__name__)
        for reqdattr in (
                ("_vb_forwardbindings", {}), ("_vb_backwardbindings", {}),
                ("_vb_weakBindingParent", None),
                ("_vb_leader_res", None),
                ("_vb_followers", None),
                ("_vb_settingAttributes", set()),
                ("_vb_delegate_attributes", {})):
            # Have to set this on dict to avoid recursing, as __setattr__
            # requires these to have already been set.  Also means we need to
            # do this before calling super, in case super sets any attrs.
            self.__dict__[reqdattr[0]] = reqdattr[1]

        self._vb_initDependencies()
        self._vb_initBindings()
        super(ValueBinder, self).__init__(**kwargs)
        if PROFILE:
            self.hit_init()

    def bind(self, frompath, topath, transformer=None, ignore_exceptions=None):
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
        if frompath.startswith('_') or topath.startswith('_'):
            raise ValueError(
                'Cannot bind private-looking attributes that start with '
                '\'_\': %r to %r' % (frompath, topath))

        log.info("Bind %r instance attribute %r to %r",
                 self.__class__.__name__, frompath, topath)
        if log.level <= logging.DETAIL and hasattr(self, frompath):
            at = getattr(self, frompath)
            if hasattr(at, "_vb_forwardbindings"):
                log.debug("Target bindings now: %r", at._vb_forwardbindings)
        self._vb_binddirection(
            frompath, topath, None, transformer, self.VB_Forward,
            ignore_exceptions)
        if log.level <= logging.DETAIL and hasattr(self, frompath):
            at = getattr(self, frompath)
            if hasattr(at, "_vb_forwardbindings"):
                log.debug(
                    "Target bindings after forward bind: %r",
                    at._vb_forwardbindings)

        self._vb_binddirection(
            topath, frompath, None, transformer, self.VB_Backward,
            ignore_exceptions)
        if log.level <= logging.DETAIL and hasattr(self, frompath):
            at = getattr(self, frompath)
            if hasattr(at, "_vb_forwardbindings"):
                log.debug(
                    "Target bindings after backward bind: %r",
                    at._vb_forwardbindings)

    def bindBindings(self, bindings):
        """Establish a set of bindings.

        :param bindings: A iterable of tuples of the form
        (frompath, topath[, transformer]).
        """
        for binding in bindings:
            transformer = None
            ignored_exceptions = None
            if len(binding) > 2:
                opts = binding[2]
                if KeyTransformer in opts:
                    transformer = opts[KeyTransformer]
                if KeyIgnoredExceptions in opts:
                    ignored_exceptions = opts[KeyIgnoredExceptions]

            try:
                self.bind(
                    binding[0], binding[1], transformer, ignored_exceptions)
            except Exception as exc:
                exc.args = (
                    str(exc.args[0]) +
                    '; '
                    'raised attempting to bind %r to %r on %r '
                    'instance' % (
                        binding[0],
                        binding[1], self.__class__.__name__),)

                raise

    def unbind(self, frompath, topath):
        """Unbind a binding. Raises NoSuchBinding() if the binding does not
        exist."""
        log.info("Unbind %r instance attribute %r to %r",
                 self.__class__.__name__, frompath, topath)

        self._vb_unbinddirection(frompath, topath, self.VB_Forward)
        self._vb_unbinddirection(topath, frompath, self.VB_Backward)

    def refreshBindings(self):
        """Pushes all forward bindings to their target again."""
        log.debug("Refresh %r instance bindings", self.__class__.__name__)
        for fromattr, adict in iteritems(
                self._vb_bindingsForDirection(self.VB_Forward)):
            for fromattrattrs, bdict in iteritems(adict):
                if len(fromattrattrs):
                    frompath = self.VB_JoinPath((fromattr, fromattrattrs))
                else:
                    frompath = fromattr
                val = self._vb_pullValue(frompath)
                for topath, cdict in iteritems(bdict):
                    log.debug("Push %r to %r", frompath, topath)
                    self._vb_push_value_to_target(val, topath, cdict)

    def unbindAll(self):
        log.debug('Unbind All from %r instance', self.__class__.__name__)
        self._vb_unbindAllCondition()

    @property
    def vb_parent(self):
        wp = self._vb_weakBindingParent
        log.detail(
            "Get vb_parent from %r instance, weakref: %s",
            self.__class__.__name__, wp)
        return wp() if wp is not None else None

    @vb_parent.setter
    def vb_parent(self, newParent):
        log.debug(
            "Set vb_parent of %r instance to %r instance",
            self.__class__.__name__, newParent.__class__.__name__)
        if newParent is None:
            self._vb_weakBindingParent = None
            return

        weakp = wref(newParent)
        self._vb_weakBindingParent = weakp

    def attributeAtPath(self, path):
        target, attr = self._vb_resolveboundobjectandattr(path)
        try:
            return getattr(target, attr)
        except AttributeError:
            raise AttributeError(
                "%r instance has no attribute at path %r." % (
                    self.__class__.__name__, path))

    def setAttributePath(self, path, value):
        target, attr = self._vb_resolveboundobjectandattr(path)
        if target is None:
            raise AttributeError(
                "%r instance has no attribute at path %r." % (
                    self.__class__.__name__, path))
        setattr(target, attr, value)

    def vb_updateAttributeBindings(self, attr, existing_val, val):

        log.debug("Update paths bound through %r.", attr)

        if isinstance(existing_val, ValueBinder):
            expar = existing_val.vb_parent
            if expar is self:
                log.debug("Unbind old attribute's parent.")
                existing_val._vb_unbindAllParent()

        if isinstance(val, ValueBinder):
            log.detail("%r value is bindable.", val.__class__.__name__)
            for direction in self.VB_Directions:
                _, _, _, bs, _ = self._vb_bindingdicts(attr, direction,
                                                       all=True)
                log.detail("Update %r bindings with %r", direction, bs)
                for subpath, bds in iteritems(bs):
                    if len(subpath) == 0:
                        continue
                    if val.vb_parent is not None and val.vb_parent is not self:
                        raise(BindingAlreadyExists(
                            "Could not update bindings for %r instance being "
                            "stored at attribute %r of %r instance as it "
                            "already has a binding parent, so is already "
                            "bound in an object graph and it cannot be bound "
                            "into more than one at a time." % (
                                val.__class__.__name__, attr,
                                self.__class__.__name__)))
                    for topath, bd in iteritems(bds):
                        subtopath = self.VB_PrependParent(topath)
                        tf = bd[KeyTransformer]
                        ie = bd[KeyIgnoredExceptions]
                        log.detail("%r bind new value %r to %r", direction,
                                   subpath, subtopath)
                        val._vb_binddirection(subpath, subtopath, self, tf,
                                              direction, ie)

        # If this attribute is forward bound, push the value out.
        _, _, _, fbds, _ = self._vb_bindingdicts(attr, self.VB_Forward,
                                                 all=True)
        log.detail(
            "forward bindings for attr %r of %r instance: %r", attr,
            self.__class__.__name__, fbds)
        for fromattrattrs, bds in iteritems(fbds):
            if len(fromattrattrs) == 0:
                for topath, bd in iteritems(bds):
                    log.detail("Push %s.%s to %s", attr, fromattrattrs,
                               topath)
                    self._vb_push_value_to_target(val, topath, bd)

    #
    # =================== MAGIC METHODS ======================================
    #
    def __getattr__(self, attr):
        """If the attribute is a delegated attribute, gets the attribute from
        the delegate, else calls super."""

        if attr.startswith('_'):
            # For perf reasons assume anything starting with '_' is not bound.
            gattr = getattr(super(ValueBinder, self), '__getattr__', None)
            if gattr is None:
                raise AttributeError(
                    "ValueBinder subclass %r has no attribute %r: perhaps it "
                    "didn't call super().__init__()?" % (
                        self.__class__.__name__, attr))
            return (attr, gattr(attr))

        log.debug("Get %r (from %r instance)", attr, self.__class__.__name__)
        sd = self.__dict__

        # Check for delegate attributes.
        if '_vb_delegate_attributes' in sd:
            log.detail('Looking for a delegate attribute')
            das = sd["_vb_delegate_attributes"]
            if attr in das:
                log.detail("Delegate attribute %r", attr)
                return getattr(getattr(self, das[attr]), attr)

        gt = getattr(super(ValueBinder, self), '__getattr__', None)
        if gt is None:
            raise AttributeError("%r instance has no attribute %r" % (
                self.__class__.__name__, attr))

        return gt(attr)

    def __setattr__(self, attr, val):
        """
        """
        if attr.startswith('_'):
            # For perf reasons assume anything starting with '_' is not bound.
            return super(ValueBinder, self).__setattr__(attr, val)

        cn = self.__class__.__name__

        if PROFILE:
            self.hit_set_attr(attr)

        log.debug("Set %r (on %r instance).", attr, cn)
        sd = self.__dict__

        # Avoid recursion if a subclass has not called init (perhaps failed
        # a part of its own initialization.
        assert "_vb_delegate_attributes" in sd, (
            "ValueBinder subclass %r has not called super.__init__()" % cn)

        # If this is a delegated attribute, pass through.
        (deleattr, dele) = self._vb_delegateForAttribute(attr)
        if deleattr is not None:
            if dele is None:
                raise AttributeError(
                    "Cannot set attribute %r on %r instance as it is "
                    "delegated to attribute %r which is None." % (
                        attr, cn, deleattr))

            log.debug('Set on delegate attribute %r', deleattr)
            return setattr(dele, attr, val)

        existing_val = getattr(self, attr, None)

        try:
            settingAttributes = sd["_vb_settingAttributes"]
            if attr in settingAttributes:
                raise RuntimeError(
                    "Recursion attempting to set attribute %r on %r "
                    "instance." % (attr, cn))
            settingAttributes.add(attr)
            try:
                super(ValueBinder, self).__setattr__(attr, val)
                # Straight away get the just set attribute. This is because
                # some descriptor properties may do something funky to the
                # value when we set it, such as parse it into an object graph
                # and set the object graph on the underlying attribute instead.
                # We trust the result of getattr() more than the argument to
                # setattr().
                initialval = val
                val = getattr(self, attr)
                if val is not initialval:
                    log.debug(
                        "%r instance %r attribute val changed after set.",
                        cn, attr)
            finally:
                settingAttributes.remove(attr)
        except AttributeError as exc:
            raise AttributeError(
                "Can't set {attr!r} on {self.__class__.__name__!r} instance: "
                "{exc}".format(**locals()))
        except RuntimeError:
            log.error(
                "Runtime error setting attribute %r on %r instance to %r. "
                "MRO is: %r.",
                attr, cn, val, self.__class__.__mro__)
            raise

        if existing_val is not val:
            self.vb_updateAttributeBindings(attr, existing_val, val)
        else:
            log.debug("New val is old val so don't update bindings.")

    def __delattr__(self, attr):
        log.detail("Del %r.", attr)

        if attr.startswith('_'):
            log.detail("Directly setting vb private attribute")
            return super(ValueBinder, self).__delattr__(attr)

        deleattr, dele = self._vb_delegateForAttribute(attr)
        if deleattr is not None:
            if dele is None:
                raise AttributeError(
                    "Attribute %r of %r instance cannot be deleted as the "
                    "delegate attribute %r is None." % (
                        attr, cn, deleattr))
            return delattr(dele, attr)

        existing_val = getattr(self, attr, sentinel)
        if existing_val is sentinel:
            raise AttributeError(
                    "Attribute %r of %r instance cannot be deleted as it does "
                    "not exist." % (attr, cn))

        self.vb_updateAttributeBindings(attr, existing_val, None)

        return super(ValueBinder, self).__delattr__(attr)

    def __del__(self):
        """We need to remove all our bindings."""
        # The weird thing about deleting an object graph like `A->B` in python
        # is that `del(B)` may be called before `delattr(A, 'B')`, so `A` may
        # still have a reference to `B` after `B` has had del(B) called.
        # Therefore we have to tolerate bindings having already been cleared up
        # in our children.
        self._vb_unbindAllCondition(tolerate_no_such_binding=True)
        sp = super(ValueBinder, self)
        dm = getattr(sp, '__del__', None)
        if dm is not None:
            dm()

    #
    # =================== INTERNAL METHODS ===================================
    #
    def _vb_unbindAllCondition(self, condition=None,
                               tolerate_no_such_binding=False):
        for direction in self.VB_Directions:
            attr_bd = self._vb_bindingsForDirection(direction)
            for attr in dict(attr_bd):
                _, _, _, bs, _ = self._vb_bindingdicts(
                    attr, direction, all=True)
                log.debug("  %d bindings through %r", len(bs), attr)
                for subpath, bds in iteritems(dict(bs)):
                    for topath, bd in iteritems(dict(bds)):
                        toattr, _ = self.VB_PartitionPath(topath)
                        log.debug("  binding %r %r -> %r", attr, subpath,
                                  toattr)
                        if condition is None or condition(attr, toattr):
                            log.debug("  unbind.")
                            path = self.VB_JoinPath((attr, subpath))
                            if not tolerate_no_such_binding:
                                self._vb_unbinddirection(
                                    path, topath, direction)
                            else:
                                try:
                                    self._vb_unbinddirection(
                                        path, topath, direction)
                                except NoSuchBinding as exc:
                                    log.debug(
                                        'NoSuchBinding %s tolerated.', exc)

    def _vb_unbindAllParent(self):
        log.debug(
            "Unbind all parent bindings of %r instance",
            self.__class__.__name__)
        return self._vb_unbindAllCondition(
            lambda attr, toattr: len(toattr) == 0)

    def _vb_resolveFromPath(self, path):
        """Returns the actual binding path, rather than one that might be
        through a dependency.

        So if a.c resolves to a.b.c, then:
        a._vb_resolveFromPath("c")
        >>> "b.c"
        """
        attr, _ = self.VB_PartitionPath(path)
        vbdas = self._vb_delegate_attributes
        if attr not in vbdas:
            log.detail("Non-delegated path %r", path)
            return path

        da = vbdas[attr]
        log.detail("Delegated path %r through %r", path, da)
        return self.VB_JoinPath((da, path))

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
                raise NoSuchBinding(path)

            attrdict = {}
            bindings[attr] = attrdict
        else:
            attrdict = bindings[attr]

        # Resolve the attrdict.
        if create:
            if attrattrs not in attrdict:
                attrdict[attrattrs] = {}

        if all:
            return bindings, attr, attrattrs, attrdict, None

        if attrattrs not in attrdict:
            raise NoSuchBinding(path)

        return bindings, attr, attrattrs, attrdict, attrdict[attrattrs]

    def _vb_push_value_to_target(self, val, topath, bdict):
        log.debug("Push value to %r", topath)
        log.detail("  value is %r", val)

        target, toattr = self._vb_resolveboundobjectandattr(topath)
        if target is not None:
            old_value = getattr(target, toattr, None)

            if val is not old_value:
                log.debug("Pushing %r to %s", val, topath)

                ie = bdict[KeyIgnoredExceptions]
                tf = bdict[KeyTransformer]
                try:
                    new_val = val
                    if tf is not None:
                        log.debug("Transform attr first")
                        new_val = tf(val)
                        log.detail("%r transformed to %r", val, new_val)
                    setattr(target, toattr, new_val)
                except Exception as thrownExc:
                    for exc in ie:
                        if isinstance(thrownExc, exc):
                            log.debug(
                                "Ignoring %r exc as is instance of %r",
                                thrownExc.__class__.__name__, exc)
                            break
                    else:
                        raise
            else:
                log.debug("Target's value already is value!")
        else:
            log.debug("Target not available to push %s", topath)

    def _vb_pullValue(self, topath):
        log.debug("Pull value from %r", topath)
        target, toattr = self._vb_resolveboundobjectandattr(topath)
        if target is None:
            return None
        return getattr(target, toattr, None)

    def _vb_binddirection(
            self, frompath, topath, parent, transformer, direction,
            ignore_exceptions):
        """
        """
        cn = self.__class__.__name__
        log.debug(
            "Bind %r of %r instance %s to %r", frompath, cn, direction, topath)
        resolvedfrompath = self._vb_resolveFromPath(frompath)
        resolvedtopath = self._vb_resolveFromPath(topath)

        # Make the attribute binding dictionary if it doesn't already exist.
        _, fromattr, fromattrattrs, _, bds = self._vb_bindingdicts(
            resolvedfrompath, direction, create=True)
        if resolvedtopath in bds:
            raise BindingAlreadyExists(
                "Attribute path %r of %r instance already bound to %r." % (
                    resolvedfrompath, cn, resolvedtopath))
        ignore_exceptions = (
            tuple() if not ignore_exceptions else ignore_exceptions)
        bd = {
            KeyTransformer: transformer,
            KeyIgnoredExceptions: ignore_exceptions
        }

        currparent = self.vb_parent
        assert (currparent is None or
                parent is None or
                currparent is parent), (
            "Attempt to bind %r instance with a %r instance parent different "
            "from its current %r instance one." % (
                cn, parent.__class__.__name__, currparent.__class__.__name__))
        if currparent is None:
            # Else is currparent is parent, so nothing to do.
            self.vb_parent = parent

        try:
            self._vb_recurse_binddirection(
                frompath, resolvedfrompath, fromattr, fromattrattrs, direction,
                topath, resolvedtopath, transformer, ignore_exceptions, bd)
        except:
            # Exception: must back out the state change we made.
            self.vb_parent = currparent
            raise

        # Seemed to work. Update dictionary.
        bds[resolvedtopath] = bd

        log.detail(
            "  %r bindings after bind %r", direction,
            self._vb_bindingsForDirection(direction))

    def _vb_recurse_binddirection(
            self, frompath, resolvedfrompath, fromattr, fromattrattrs,
            direction, topath, resolvedtopath, transformer, ignore_exceptions,
            bd):
        if fromattrattrs:
            # This is an indirect binding, so recurse if possible.
            # E.g.
            # self.bindforward("a.b", "c")
            # >> self.a.bindforward("b", ".c")
            log.debug("indirect %s binding %r -> %r", direction, frompath,
                      resolvedtopath)
            if len(fromattr) == 0:
                # Parent in the from path.
                log.debug("  parent in frompath")
                fromattr_resolved = "vb_parent"
                subobj = parent
            else:
                fromattr_resolved = fromattr
                subobj = getattr(self, fromattr_resolved, None)

            if isinstance(subobj, ValueBinder):
                log.debug("  child is VB compatible.")
                subobj._vb_binddirection(
                    fromattrattrs, ValueBinder.PS + resolvedtopath, self,
                    transformer, direction, ignore_exceptions)
            elif subobj is not None:
                raise TypeError(
                    'Attempt to bind path %r (resolved as %r) of %r instance '
                    'to path %r (resolved as %r) failed as the first '
                    'attribute at '
                    '%r was not a ValueBinder instance (was %r '
                    'instance).' % (
                        frompath, resolvedfrompath,
                        self.__class__.__name__, topath, resolvedtopath,
                        fromattr_resolved, subobj.__class__.__name__))
        else:
            # This is a direct binding. If we already have a value for it, set
            # the target. E.g.
            # self.bindforward("c", ".a")
            # >> self._vb_parent.a = self.c
            log.debug("direct %r binding %r -> %r", direction, frompath,
                      resolvedtopath)
            if direction == self.VB_Forward:
                val = getattr(self, fromattr, sentinel)
                if val is not sentinel:
                    log.debug("  Has child attr %r", fromattr)
                    self._vb_push_value_to_target(val, resolvedtopath, bd)
            else:
                log.debug("Pull value.")
                val = self._vb_pullValue(resolvedtopath)
                self._vb_push_value_to_target(val, fromattr, bd)

    def _vb_unbinddirection(self, frompath, topath, direction):
        """Unbind a particular path.

        Say "c.d" is bound forward to ".e.f" on b (the parent of b is a).

        b._vb_unbinddirection("c.d", ".e.f", VB_Forward)

        would undo this, and recurse to do:
        b.c._vb_unbinddirection("d", "..e.f", VB_Forward)
        """
        log.debug("%r(%r) %r bindings before unbind %r",
                  self.__class__.__name__, id(self), direction,
                  self._vb_bindingsForDirection(direction))

        resolvedfrompath = self._vb_resolveFromPath(frompath)
        resolvedtopath = self._vb_resolveFromPath(topath)

        bindings, fromattr, fromattrattrs, attrbindings, _ = (
            self._vb_bindingdicts(resolvedfrompath, direction, create=False))

        if len(fromattr) == 0:
            fromattr_resolved = "vb_parent"
        else:
            fromattr_resolved = fromattr

        if len(fromattrattrs) > 0 and hasattr(self, fromattr_resolved):
            attrtopath = self.VB_PrependParent(resolvedtopath)
            child = getattr(self, fromattr_resolved)

            # If the child doesn't support ValueBinder, then it is a bit late
            # to do anything about this now! This will have been logged when
            # we attempted to set the binding on it, so just ignore it now.
            # TODO: should just assert and not quietly ignore this?
            if isinstance(child, ValueBinder):
                try:
                    child._vb_unbinddirection(
                        fromattrattrs, attrtopath, direction)
                except NoSuchBinding as exc:
                    exc.args += (
                        "Attempted unbind on %r attribute of %r instance" % (
                            fromattr_resolved, self.__class__.__name__),)
                    raise

        frompathbds = attrbindings[fromattrattrs]
        del frompathbds[resolvedtopath]
        if len(frompathbds) == 0:
            del attrbindings[fromattrattrs]
            if len(attrbindings) == 0:
                del bindings[fromattr]

        self._vb_maybeReleaseParent()

        if PROFILE and log.getEffectiveLevel() <= logging.DEBUG:
            log.debug("  %r bindings after unbind %r",
                      direction,
                      self._vb_bindingsForDirection(direction))

    def _vb_maybeReleaseParent(self):

        def _attrGen():
            for _bd in (self._vb_forwardbindings, self._vb_backwardbindings):
                for _fa, _fabs in iteritems(_bd):
                    yield _fa
                    for _ta in _fabs:
                        yield _ta
        log.debug(
            '  Maybe release parent, bindings: %r %r',
            self._vb_forwardbindings, self._vb_backwardbindings)
        for attr in _attrGen():
            log.debug('Check immediate binding on attr %r', attr)
            if attr == '':
                log.debug("Parent is still in binding paths")
                break
        else:
            log.debug("Parent is not in binding paths")
            self.vb_parent = None

    def _vb_resolveboundobjectandattr(self, path):
        log.debug("resolve path %r", path)
        nextobj = self
        splitpath = self.VB_SplitPath(path)
        for nextattr in splitpath[0:-1]:

            nalen = len(nextattr)
            if nalen == 0:
                nextattr = "vb_parent"

            log.debug("  try next attribute %r", nextattr)
            nextobj = getattr(nextobj, nextattr, sentinel)
            if nextobj is sentinel:
                # This we're missing an object in the path, so need to return
                # None.
                log.debug("  missing")
                nextobj = None
                nextattr = None
                break

            continue

        else:
            nextattr = splitpath[-1]
        return nextobj, nextattr

    def _vb_initDependencies(self):
        if not hasattr(self, "vb_dependencies"):
            return

        log.debug("%r has VB dependencies", self.__class__.__name__)
        deps = self.vb_dependencies
        deleattrmap = self._vb_delegate_attributes
        for dele, deleattrs in deps:
            for deleattr in deleattrs:
                if deleattr in deleattrmap:
                    raise ValueError(
                        "Delegate attribute %r declared twice" % deleattr)
                log.debug("Attr %r is delegated through %r", deleattr, dele)
                deleattrmap[deleattr] = dele

    def _vb_initBindings(self):
        if not hasattr(self, "vb_bindings"):
            return

        self.bindBindings(self.vb_bindings)

    def _vb_delegateForAttribute(self, attr):
        sd = self.__dict__
        das = sd['_vb_delegate_attributes']
        if attr not in das:
            return None, None

        deleattr = das[attr]
        log.debug(
            "%r instance pass delegate attr %r to attr %r",
            self.__class__.__name__, attr, deleattr)
        dele = getattr(self, deleattr)
        return deleattr, dele
