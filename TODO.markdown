### TODO for SIP party. ###

## List. ##

1. All UTs pass.
2. TCP support. 
3. SIPP test integration.
4. REGISTER dialogues.
5. INVITEs with media sessions.
6. Pumba integration.
7. Continuous Integration.
8. Example scripts.
9. Proper python3 support.
10. Get rid of "delegateattributes", use "vb_dependencies".
11. Get rid of exceptions being thrown  when attempting unbinds in the Message destructor.
12. Header custom parse is very simplistic in working out how to split up the fields. Need to consult the RFC and work out the authoritative way of doing it.
    a. Message parse should not simplistically cut up lines based on newlines. It should probably be cut up based on re.split() using {CRLF}{token}{COLON}
    b. Header should be passed {token}{COLON}[contents up to next {CRLF}{token}{COLON} or {CRLF}{CRLF}]. Header should do an initial parse to deduce the subclass and pass on the contents to the subclass to parse. So receiving:
    To: alice@atlanta.com\r\n\r\n
    Header receives:
    To: alice@atlanta.com
    ToHeader receives:
     alice@atlanta.com
13. Move sipheader out of util and probably into prot.
14. Offers SDP.
15. Document and fixing attribute naming convention in vb.py.
 
## Done list. ##

1. Move transport to sipparty not sipparty/sip -- done 10/08/2015
2. Smart UT logging system. -- done 12/08/2015

## Changelog ##

10/08/2015 - first draft of TODO list.

## Problems ##

### When a VB instance is set on an attribute on another VB instance due to a binding action, where is its parent? ###

14/08/2015 - semi-solved using number 3, although policing of the restrictions is not very good.

    a.bind("a", "b.aa")
    a.a = aa
    a.b = ab
    >> a.b.aa == a.a

So is `a` `aa`'s parent, or is `ab`?

Potential solutions:

1. The parent is the item it was first set on.
    a. We can latch the vb into that place, based on parent item ID and attribute name.
    b. If it is set on another hot path, it is not rebound. Which means that you can't bind paths through a destination binding, but you can bind the 'to' attribute to another, if you really want. I.e.

        a.bind("b", "c")
        a.bind("c.a", "a")  # ILLEGAL.
        a.bind("c", "d.c")  # OK.

2. We can have multiple parents. Each binding tracks its own parent.

        a.a = aa
        a.b = ab
        a.bind("a", "b.aa")
        a.bind("a.a", "c.a")
        a.bind("b.aa.b", "d.b")

    The bindings of `aa` are now `"a" -> ".c.a"` with parent `a`, and `"b" -> "..d.b"`, with parent `b`.

    But now, when pushing values to a parent, how can we choose the right path, as we have no way to know what attribute of the parent we are, so the parent itself cannot determine uniquely its parent for the attribute.

3. You can't add bindings between two direct attributes of the same object. So the following are illegal:
    
        a.bind("a", "b")
        a.bind("a.a.a", "a.a.b")

Also it is illegal to bind from a target path, e.g.:

    a.bind("a", "b")
    a.bind("b.c", "c")  # ILLEGAL

Otherwise object at `"a"` would have two parents (albeit in this case the same object `a`).

This could be enforced at this simple level in the `bind` method, but since this won't cover all cases, it is enforced in the `_vb_binddirection` method, which refuses to allow a parent to be set which is not the current parent.