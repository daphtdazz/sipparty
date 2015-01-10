"""Utility functions for py-sip.
"""


class attributetomethodgenerator(type):
    """Metaclass that catches unknown class attributes and calls a class method
    to generate an object for them."""
    def __getattr__(cls, name):
        return cls.generateobjectfromname(name)
