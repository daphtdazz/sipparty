# sipparty <a href="http://travis-ci.org/daphtdazz/sipparty">![Travis status](https://img.shields.io/travis/daphtdazz/sipparty.svg?branch=master)</a> #

## Overview ##

This project implements a SIP stack and provides tools for holding SIP media sessions with other SIP speakers. It is written entirely in Python using standard libraries with support for python 2.7 and >=3.5, and attempts to provide a dead-easy and idiomatic API for python clients.

There is an iPython tutorial to get started with at **SIP Party tutorial.ipynb**. Docs are generated using sphinx but still a work in progress.

Tested on CentOS 6 and the latest Mac OS X public release. Windows support is unlikely.

## Install ##

Clone from github, `cd` to the root directory and install the requirements using

    pip install -r requirements.txt

If you want to edit and build the docs, use

    pip install -r docs_requirements.txt

as well.

## Key features ##

### High-level interaction with dialogs ###

Create a SIP 'party' and start a phone call. The most basic party is the one that doesn't actually advertise any media.

    from sipparty.parties import NoMediaSimpleCallsParty
    party =  NoMediaSimpleCallsParty(aor='alice@atlanta.com')
    dialog = party.invite('bill@biloxi.com')
    dialog.terminate()

### Smart object graphs ###

Very flexible API for configuring objects using the `sipparty.deepclass.DeepClass` class.

    from sipparty.parties import NoMediaSimpleCallsParty
    party =  NoMediaSimpleCallsParty()
    party.uri = 'sip:alice@atlanta.com'

    # Is the same as
    party.aor = 'alice@atlanta.com'

    # Is the same as
    party.username = 'alice'
    party.host = 'atlanta.com'

    # Is the same as
    from sipparty.sip.components import URI
    party.uri = URI(aor='alice@atlanta.com')

### Smart transport layer reusing sockets as much as possible ###

Creating multiple parties with the default settings only results in a single listen socket.

    from sipparty.parties import NoMediaSimpleCallsParty
    from sipparty.sip.siptransport import SIPTransport

    parties = [
        NoMediaSimpleCallsParty(aor='test%d@test.com' % (test + 1,))
        for test in range(100)]
    map(lambda x: x.listen(), parties)

    # The transport is implemented using sipparty.util.Singleton which
    # provides a powerful and simple Singleton design pattern implementation.
    tp = SIPTransport()
    tp.listen_socket_count
    > 1

### Powerful FSM implementation for maintaining call state ###

Dialog state is maintained by inheriting from the `sipparty.fsm.FSM` class, allowing for easy debuggability of state changes and understandable exceptions when an illegal input is applied in a given state.

*And more...*


