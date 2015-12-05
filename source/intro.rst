Introduction
============

**sipparty** is a python module providing high and low-level classes and routines for creating, manipulating, controlling, sending, receiving and extending SIP (Session Initiation Protocol) messages, components, dialogs and state, and defining SDP (Session Description Protocol) sessions for media negotiation.

The top-level object is the ``Party`` object, which represents the SIP User Agent. To be useful this must be created with a logic description for the dialogs that it will be able to participate in, and the media session it will be able to offer. Convenience subclasses of ``Party`` are provided for standard dialog types. A simple script using the ``Party`` object to start and end an ``INVITE`` dialog would look as follows::

    from sipparty.parties import SingleRTPSessionSimplenParty
    from sys import (exit, stderr)
    from time import sleep

    my_party = SingleRTPSessionSimplenParty(b'alice@atlanta.com')
    invite_dialog = my_party.invite(b'bob@biloxi.com', proxy='10.0.0.2')

    # The dialog is asynchronous, and will connect or fail on a separate
    # thread. For this simple script we will wait for it to finish initiating
    # dialog.
    invite_dialog.waitForStateCondition(
        lambda state: state != invite_dialog.States.InitiatingDialog)

    if invite_dialog.state == invite_dialog.States.Error:
        print(
            'Failed to connect to %(uri)s. Error was: %(dialog_error)s' %
            {'uri': 'bob@biloxi.com',
             'dialog_error': invite_dialog.last_error},
             file=stderr)
        exit(1)

    sleep(30)

    invite_dialog.terminate()
    invite_dialog.waitForStateCondition(
        lambda state: state != invite_dialog.States.TerminatingDialog)

    if invite_dialog.state == invite_dialog.States.Error:
        print(
            'Failed to terminate dialog to %(uri)s cleanly. Error was: '
            '%(dialog_error)s' %
            {'uri': 'bob@biloxi.com',
             'dialog_error': invite_dialog.last_error},
             file=stderr)
        exit(2)

    exit(0)



