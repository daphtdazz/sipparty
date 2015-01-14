import sip
import sys

class A(object):
    objs = []

class AA(A):
    objs = A.objs + [2]

def afunc():
    print "afunc"

afunc(a="a")

print(AA.objs)

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
