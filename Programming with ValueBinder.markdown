# Programming with ValueBinder #

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
