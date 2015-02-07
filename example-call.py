import sip
import sys
import pdb
import sip._util


class A(object):
    attr = 1234


class B(A):
    attr = 4321

    @classmethod
    def getattr(cls):
        return super(cls, None).attr

print(B.getattr())

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
