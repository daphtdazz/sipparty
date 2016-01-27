<<<<<
SIP/2.0 200 OK\r\n
From: <sip:bob@biloxi.com>;tag=2f126347\r\n
To: <sip:alice@atlanta.com>;tag=6e8b019b\r\n
Via: SIP/2.0/UDP [::1]:55784;branch=z9hG4bK5ffb444c9bbe8442\r\n
Call-ID: b55204-20160124234729\r\n
CSeq: 908738945 INVITE\r\n
\r\n
<<<<<
DEBUG:sipparty.sip.siptransport:SIPTransport attempting to consume 218 bytes.
DEBUG:sipparty.sip.siptransport:Full message
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> not cancelled, next retry times: [], wait: 0.020000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> wait on dict_keys([13]).
INFO:sipparty.sip.siptransport:Message parsed.
ERROR:sipparty.fsm.retrythread:Exception (1st) processing new data for selectable <socket.socket fd=10, family=AddressFamily.AF_INET6, type=SocketKind.SOCK_DGRAM, proto=0, laddr=('::1', 55784, 0, 0), raddr=('::1', 5060, 0, 0)> (fd 10):
Traceback (most recent call last):
  File "/Users/daphtdazz/github/sipparty/sipparty/fsm/retrythread.py", line 70, in newDataAvailable
    self._fds_action(self._fds_selectable)
  File "/Users/daphtdazz/github/sipparty/sipparty/util.py", line 738, in weak_method
    return getattr(sr, method)(*pass_args, **pass_kwargs)
  File "/Users/daphtdazz/github/sipparty/sipparty/transport.py", line 536, in socket_selected
    return self._dgram_socket_selected()
  File "/Users/daphtdazz/github/sipparty/sipparty/transport.py", line 564, in _dgram_socket_selected
    self._readable_socket_selected()
  File "/Users/daphtdazz/github/sipparty/sipparty/transport.py", line 593, in _readable_socket_selected
    dc(self, addr, data)
  File "/Users/daphtdazz/github/sipparty/sipparty/util.py", line 738, in weak_method
    return getattr(sr, method)(*pass_args, **pass_kwargs)
  File "/Users/daphtdazz/github/sipparty/sipparty/sip/siptransport.py", line 163, in sipByteConsumer
    assert data[:3] == b'INV'
AssertionError
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> not cancelled, next retry times: [], wait: 0.320000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> wait on dict_keys([10, 6, 7]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> not cancelled, next retry times: [], wait: 0.040000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> wait on dict_keys([13]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> not cancelled, next retry times: [], wait: 0.320000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> wait on dict_keys([9]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> not cancelled, next retry times: [], wait: 0.080000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> wait on dict_keys([13]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> not cancelled, next retry times: [], wait: 0.160000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> wait on dict_keys([13]).
DEBUG:sipparty.fsm.retrythread:Cancel retrythread SimpleCall2.retry_thread
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> Trigger spin
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> process [13], [], []
DEBUG:sipparty.fsm.retrythread:New data available for selectable <socket.socket fd=13, family=AddressFamily.AF_UNIX, type=SocketKind.SOCK_STREAM, proto=0>.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall2.retry_thread, started 123145318068224)> thread exiting.
INFO:sipparty.fsm.retrythread:__del__ SimpleCall2.retry_thread RetryThread
DEBUG:sipparty.fsm.retrythread:Cancel retrythread SimpleCall1.retry_thread
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> Trigger spin
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> process [9], [], []
DEBUG:sipparty.fsm.retrythread:New data available for selectable <socket.socket fd=9, family=AddressFamily.AF_UNIX, type=SocketKind.SOCK_STREAM, proto=0>.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SimpleCall1.retry_thread, started 123145312813056)> thread exiting.
INFO:sipparty.fsm.retrythread:__del__ SimpleCall1.retry_thread RetryThread
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> not cancelled, next retry times: [], wait: 0.640000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> wait on dict_keys([10, 6, 7]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> not cancelled, next retry times: [], wait: 1.280000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> wait on dict_keys([10, 6, 7]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> not cancelled, next retry times: [], wait: 2.560000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> wait on dict_keys([10, 6, 7]).
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> process [], [], []
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> check timers
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> not cancelled, next retry times: [], wait: 5.120000. Master thread is alive: True.
DEBUG:sipparty.fsm.retrythread:<RetryThread(SIPTransport.retryThread, started 123145307557888)> wait on dict_keys([10, 6, 7]).
E
======================================================================
ERROR: test_weak_references (sipparty.test.testparty.TestPartyWeakReferences)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/Users/daphtdazz/github/sipparty/sipparty/test/testparty.py", line 224, in test_weak_references
    WaitFor(lambda: wtp1() is None, 5)
  File "/Users/daphtdazz/github/sipparty/sipparty/util.py", line 765, in WaitFor
    raise Timeout("Timed out waiting for %r" % condition)
sipparty.util.Timeout: Timed out waiting for <function TestPartyWeakReferences.test_weak_references.<locals>.<lambda> at 0x108a23510>

----------------------------------------------------------------------
Ran 1 test in 5.641s

FAILED (errors=1)
INFO:sipparty.transport:Closing all sockets.
INFO:sipparty.fsm.retrythread:__del__ SIPTransport.retryThread RetryThread
