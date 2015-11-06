# sip-party

.. image:: https://img.shields.io/travis/daphtdazz/sipparty/develop.svg
           :target: http://travis-ci.org/daphtdazz/sipparty

## Layout

## Message

### Attributes

- startline
- headers
- bodies

### Types

- INVITE

## Header

### Attributes

-   value
    By default the first item in values. A Field object.
-   values
    A list of all the values for the Header.

## Field

-   value
    An object that can be stringified.
-   parameters
    A Parameters object that contains all the parameters of the Field, indexed
    by name.
