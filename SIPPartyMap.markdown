# SIP Party Map #

    Message
      startline <- Request
      headers
      bodies

    Request
      type
      uri --> ToHeader.uri
      protocol

    Header
      fields <- [Field, ...]
      parameters

    FieldDelegateHeader <= Header
      FieldDelegateClass = ??

    FromHeader <+= FieldDelegateHeader
    ToHeader   <+
      FieldDelegateClass = field.DNameURIField
      dname (d field.value)
      uri (d field.value)

    Field
      value
      parameters

    DNameURIField <= Field
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

# SIP Scenario #

