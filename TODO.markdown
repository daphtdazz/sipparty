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
 
## Done list. ##

1. Move transport to sipparty not sipparty/sip -- done 10/08/2015
2. Smart UT logging system. -- done 12/08/2015

## Changelog ##

10/08/2015 - first draft of TODO list.
