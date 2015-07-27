# Programming with sipparty #

## TODO ##

-   Synchronous `hit` on asynchronous FSM. 
-   Singletonise the retrythread. 
-   ?? Make retry thread smarter about owning thread; allow it not to be owned.
-   ?? FSM should probably not switch state if the action raises.

## Message ##

Access headers on a message using message.<type>Header.

## Headers ##

### `field` and `fields` property ###

The `field` object is a special property on the `Header` class and may not be overridden in subclasses. 

To customize, write a property named  `fields` if you wish and return a list of the fields for the header. `field` will automatically refer to the first of `fields`. However, you must implement both the getter and setter, even if you only want to override reading in certain situations, because a property is a *data descriptor* which takes precedence over the dictionary   E.g. `Contact` does this to support the star contact header.

?? Can I get around that by implementing fields as a derived property, and thus subclasses can override by using another derived property with custom getters ??

For simple a subclass has no need for multiple fields, they may override 

Autogeneration of headers (i.e. population of the `fields` attribute) occurs during `Header.__init__` with the following precedence:

1. If the kwarg `fields` are passed in at initialization, these are used.
1. If the class implements `autogenFields`, this is called.
2. Else if the class has a `FieldClass` property, `fields` is initialized to `[FieldClass()]`.
3. Else fields is left as an empty list.

## Transport ##



? No overriding of fields as properties?
? How to trigger autogeneration?

Bindings should only be made through `field`. ???
