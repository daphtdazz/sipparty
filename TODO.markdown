### TODO for SIP party. ###

## List. ##

1. Don't use 0.0.0.0 DGRAM listen sockets for sending from.
2. UDP transport retrying.
   a.  Should have a dialog manager. -- initial done 8/5/2016
   b.  Party should have transaction manager, dialog manager, transport -- initial done 8/5/2016
   c.  Need to check flows are now correct and transaction lifetimes work. In particular UTs for dialog + transaction interactions (check transaction retries for all types, + 1XX provisional responses)
3. REGISTER dialogues.
4. TCP support.
5. Move "Programming guides" into a section of the documentation.
9. Smarter ACK than simply "ACK all 200s" in dialog.py
10. expiry timer for invites
11. The mechanism for determining the correct response type to input is not thread-safe.
12. the name for inputs into server dialogs to indicate "respond with XXX" is response_XXX when it should be "respond_XXX" which is more consistent with transaction.
11. Refactor singleton out of util.
12. message.isrequest replace with property is_request
13. Make util a package with sub-modules.
10. Get rid of "delegateattributes", use "vb_dependencies". -- ?? semi done?
12. Move sipheader out of util and probably into prot.
15. Document and fixing attribute naming convention in vb.py.
16. deepclass representation is overly verbose / not detailed enough depending on whether we recurse to superclass's deepclasses.
17. retrythread is heavyweight: should be able to share retrythreads amongst multiple async FSMs / users (e.g. Transactions!)
18. Better handling of attempt to pass an unrecognised kwarg into DeepClass.__init__().
19. Cumulative field_bindings for Message classes.
20. Short form header names.
21. ParseError should have SIPParseError subtype which should have a response code field so siptransport can know what response code to send.
23. Generate remote session from SDP received and send data to from it.
24. Collapse AOR into URI.
25. quoted-string in display-name in name-addr cannot be followed by LWS??
26. Parser only copes with binary types...
27. Disable checking on deepclass attributes.
28. Allow the DeepClass attribute dictionary to be a list / tuple of (key, value) tuples to enforce ordering.
29. OnlyWhenLocked decorator should allow the lock attribute name to be specified in its constructor.
30. Use bridge pattern to make FSM more lightweight and allow asynchronous flexibility

## Done list. ##

1. Move transport to sipparty not sipparty/sip -- done 10/08/2015
2. Smart UT logging system. -- done 12/08/2015
3. Get rid of exceptions being thrown  when attempting unbinds in the Message destructor. -- done 11/08/2015
4. All UTs pass. -- done 17/08/2015
5. Header custom parse is very simplistic in working out how to split up the fields. Need to consult the RFC and work out the authoritative way of doing it.
    a. Message parse should not simplistically cut up lines based on newlines. It should probably be cut up based on re.split() using {CRLF}{token}{COLON}
    b. Header should be passed {token}{COLON}[contents up to next {CRLF}{token}{COLON} or {CRLF}{CRLF}]. Header should do an initial parse to deduce the subclass and pass on the contents to the subclass to parse. So receiving:
    To: alice@atlanta.com\r\n\r\n
    Header receives:
    To: alice@atlanta.com
    ToHeader receives:
     alice@atlanta.com
   -- done 14/08/2015
6. INVITEs with media sessions. -- done 23/08/2015
7. 200s with media sessions. -- done 23/08/2015
8. SIPP test integration -- done 4/09/2015
9. Fix slow UT termination time (weak reference needed somewhere?) -- done 05/09/2015
10. Proper python3 support.
    a. 'bytes' does not support % and .format(), so need to use BytesGenner and str instead where appropriate.
11. Resource Warnings under python3.
12. Continuous Integration - using travis 31/10/2015.
13. Example scripts - done initial ipython demo 31/1/2016
14. Cache Datagram sockets for faster allocation of a socket when sending data - sockets are reused by default 31/1/2016
15. SIPTransport could allow force override to get a new listen socket - done 31/06/2016: can request not to reuse a socket in `Transport.listen_for_me`

## Changelog ##

10/08/2015 - first draft of TODO list.
04/09/2015 - list at point of ability to make an entire call.
01/02/2016 - list after re-working transport to support socket re-use.

## Problems ##

### What is the design for the media session?  ###

1. Media session

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
