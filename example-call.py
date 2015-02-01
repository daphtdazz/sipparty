import sip
import sys
import pdb
import sip._util

class AA(object):
    def __getattribute__(self, attr):
        print("AA getattribute")
        return getattr(super(AA, self), attr)

class A(AA):
    objs = []

    def __init__(self):
        super(A, self).__init__()
        self.a = 1

    def __contains__(self, attr):
        print("A contains: " + attr)
        if attr == "special":
            return True

        return False

    def __getattr__(self, attr):
        print("A.__getattr__: {attr}".format(**locals()))
        if attr == "special":
            return "special"

        return getattr(super(A, self), attr)


class B(sip._util.ValueBinder, object):

    def __init__(self):
        super(B, self).__init__()
        self.b = None

print "get an A"
a = A()

if hasattr(a, "special"):
    print "has special!"

if getattr(a, "notspecial"):
    print "has not special!"
else:
    print "has not notspecial"


sys.exit(0)

# Not yet implemented
caller = sip.Party()
callee = sip.Party()

callee.listen()

caller.register()

callee.receiveRegister()
callee.respond(200)

caller.receiveResponse(200)

caller.invite()
callee.respond(100)
callee.respond(180)
caller.receiveResponse(100)
caller.receiveResponse(180)

callee.bye()
caller.respond(200)
