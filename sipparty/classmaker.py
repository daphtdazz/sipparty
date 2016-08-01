"""Resolve metaclass conflicts.

Large part copied from Michele's recipe
http://code.activestate.com/recipes/204197-solving-the-metaclass-conflict/
modified for flake8 purposes and to add some utilities at the end.

Licensed under the `PSF license<https://docs.python.org/3/license.html>`_, and
written by Michele Simionato, David Park and with input by others.

And many thanks to him because this solves a thorny problem, good work!
"""

from functools import partial
import inspect
from six import iteritems, PY2
import types
# import __builtin__


#
# preliminary: two utility functions
#
def _skip_redundant(iterable, skipset=None):
    """Redundant items are repeated items or items in the original skipset."""
    if skipset is None:
        skipset = set()
    for item in iterable:
        if item not in skipset:
            skipset.add(item)
            yield item


def _remove_redundant(metaclasses):
    if PY2:
        skipset = set([types.ClassType])
    else:
        skipset = set()
    for meta in metaclasses:  # determines the metaclasses to be skipped
        skipset.update(inspect.getmro(meta)[1:])
    return tuple(_skip_redundant(metaclasses, skipset))

#
# now the core of the module: two mutually recursive functions
#
memoized_metaclasses_map = {}


def _get_noconflict_metaclass(bases, left_metas, right_metas):
    # make tuple of needed metaclasses in specified priority order
    metas = left_metas + tuple(map(type, bases)) + right_metas
    needed_metas = _remove_redundant(metas)
    # return existing confict-solving meta, if any
    if needed_metas in memoized_metaclasses_map:
        return memoized_metaclasses_map[needed_metas]
    # nope: compute, memoize and return needed conflict-solving meta
    elif not needed_metas:         # wee, a trivial case, happy us
        meta = type
    elif len(needed_metas) == 1:  # another trivial case
        meta = needed_metas[0]
    # check for recursion, can happen i.e. for Zope ExtensionClasses
    elif needed_metas == bases:
        raise TypeError("Incompatible root metatypes", needed_metas)
    else:  # gotta work ...
        metaname = '_' + ''.join([m.__name__ for m in needed_metas])
        meta = classmaker()(metaname, needed_metas, {})
    memoized_metaclasses_map[needed_metas] = meta
    return meta


def classmaker(left_metas=(), right_metas=()):
    """Return a automatically-correct metaclass generator."""
    def make_class(name, bases, adict):
        metaclass = _get_noconflict_metaclass(bases, left_metas, right_metas)
        return metaclass(name, bases, adict)
    return make_class


# Utilities added to Michele's recipe to make it easier to write python2 and
# python3 compatible classes without metaclass conflicts.
def _full_class_builder(mc, bases, shell_class):

    bases = [
        bb for bb in bases
        if bb is not object
    ]
    bases.append(object)
    bases = tuple(bases)

    lms = (mc,) if isinstance(mc, type) else mc

    # We can't just put the shell class in the inheritance hierarchy,
    # because this will break super() within the shell class, so rip out its
    # innards to create an entirely new class.
    new_class = classmaker(left_metas=lms)(
        shell_class.__name__, bases, {
            k: v for k, v in iteritems(shell_class.__dict__)
            if k != '__dict__'})
    return new_class


def classbuilder(bases=(), mc=()):
    return partial(_full_class_builder, mc, bases)

__all__ = ['classmaker', 'classbuilder']
