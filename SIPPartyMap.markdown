# SIP Message Map #

    Message
      startline <- Request
      headers
      bodies

      # Magic methods:
      <headertype>Header  # E.g. toHeader

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

    ViaHeader <= FieldDelegateHeader
      FieldDelegateClass = ViaField
      protocol (d field.protocol)
      transport (d field.transport)
      host (d field.host)

    ContactHeader <= FieldDelegateHeader
      FieldDelegateClass = field.DNameURIField
      isStar
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

    TransportFSM
      localAddress
      localAddressHost (p localAddress[0])
      localAddressPort (p localAddress[1])

# SIP Party Map #

    Party
      aor
      scenario
      transforms
      transport
