# Programming with ValueBinder #

## Declaring bindings for a class. ##

To declare bindings for all instances of a class in the class definition, use a `vb_bindings` class attribute list of bindings, such as:

    class MyValueBinder(vb.ValueBinder):
        vb_bindings = (
            ("a", "b"),
            ("a", "c", lambda a: a.lower()))

The second example illustrates use of a transformer. Whenever `a` is changed, `c` is set to the result of the lambda acting on `a`.

## Delegated Attributes ##
ValueBinder provides a way to implement delegated attributes. Say you had an object `a` with attribute `a.b`, and whenever someone set `c` on `a` (e.g. `a.c = 5`) you wanted to pass that through to `b`, essentially doing `a.b.c = 5`. (This can be useful in classes sharing code / interfaces by composition rather than inheritance.) In this case you can declare `vb_dependencies` class attribute for you object that has a list of delegated attributes, such as:

    class A(vb.ValueBinder):
        vb_dependencies = (
            ("b", ["c", "d"])
        )

This declares that whenever one of the attributes `"c"` or `"d"` is set on an instance of `A`, that attribute should passed through to the subattribute `b` instead (if it is not there `AttributeError` is raised).

### Implementation notes ###
To ensure that this works, `ValueBinder` simply normalizes any binding that it is requested to perform before creating it. So continuing the example from above:

    a = A()
    a.bind("c", "e")

Is equivalent to:

    a = A()
    a.bind("b.c", "e")

The dictionaries which store binding information for properties of objects are called `_vb_forwardbindings` and `_vb_backwardbindings`. These have the following format:

    {
        <bound attribute>: {
            <attribute path of attribute bound>: {
                <path of attribute bound to>: { <properties of binding> }
            }
        }
    }

So some examples: 

    self.bind('a.b.c', 'd.e.f')
    self._vb_forwardbindings = {
        'a': {
            'b.c': {
                'd.e.f': {}
            }
        }
    }s

## Subclassing ##

### Required work. ###

The following methods, if implemented in subclasses, must invoke `super`'s method to ensure correct binding behaviour.

    __init__
    __del__
    __getattr__
    __setattr__

## Known problems ##

### Putting non-ValueBinder instances in the binding path ###

If you attempt to bind a path which has an existing non-None and non-ValueBinder instance in the binding path, the call will raise a TypeError. Also the internal state of the object is not guaranteed to be the same as it started, but it should behave in the same way (i.e. dictionaries may have been pre-emptively created but subsequently left empty since the bind failed).

E.g.

    a = ValueBinder()
    b = NonValueBinder()
    a.b = b
    a.bind('b.c', 'another_attribute')
    >> raises TypeError since 'b' does not inherit from ValueBinder.

However, if you attempt to set a non-ValueBinder object into a binding path, then this will quietly be allowed. This is considered a bug since it can be hard to work out what the problem is if you have forgotten you didn't make a particular subclass inherit from ValueBinder.

E.g.
    a = ValueBinder()
    b = NonValueBinder()
    a.bind('b.c', 'another_attribute')
    a.b = b
    >> Should but does not raise TypeError.
    
