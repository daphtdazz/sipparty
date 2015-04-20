SIP Party Map
=============

    Message
      startline <- Request
      headers
      bodies

    Request
      type
      uri --> ToHeader.uri
      protocol

    Header
      value
      parameters

    FieldDelegateHeader <= Header
      FieldDelegateClass = ??

    FromHeader <+= FieldDelegateHeader
    ToHeader   <+
      FieldDelegateClass = field.PartyIDField
      dname (d value.value)
      uri (d value.value)

    Field
      value
      parameters

    PartyIDField <= Field
      dname (d value)
      uri (d value)

    DNameURI
      dname
      uri

    URI
      scheme
      aor

    AOR
      username
      host

    Host
      address  # reformat of Host in form that can be passed to socket code.

SIP Scenario
============

