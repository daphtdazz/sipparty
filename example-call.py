import sip
import sys
import pdb
import sip._util


class A(sip._util.ValueBinder, object):
    objs = []

    def __init__(self):
        super(A, self).__init__()
        self.a = 1


class B(sip._util.ValueBinder, object):

    def __init__(self):
        super(B, self).__init__()
        self.b = None


a = A()
b = B()

a.bind("a", "b")

a.a = 1
print a.b
a.a = 2
print a.b
a.b = 3
print a.a

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
