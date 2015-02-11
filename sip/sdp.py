"""sdp.py

Code for handling Session Description Protocol

Copyright 2015 David Park

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
import logging
import _util
import vb
import prot
from parse import Parser

log = logging.getLogger(__name__)


class SDPNoSuchDescription(Exception):
    pass


class Body(Parser, vb.ValueBinder):
    """SDP is a thankfully tightly defined protocol, allowing this parser to
    be much more explicit. The main point is that there are 3 sections:

    Session Description (one)
    Time Description (one)
    Media Description (one or more)

    For sanity, sdp.Body expands the first two (so sdp.body.version gives you
    the version description), and the medias attribute is a list formed by
    parsing MediaDesc, which is a repeating pattern.

    The SDP spec says something about multiple session descriptions, but I'm
    making the initial assumption that in SIP there will only be one.
    """

    longnamestuple = (
        "version",
        "owner",
        "sessionname",
        "info",
        "uri",
        "email",
        "phone",
        "connectioninfo",
        "bandwidthinfo",
        "time",
        "timezone",
        "encryptionkey",
        "attributes",
        "media")
    longnamesenum = _util.Enum(longnamestuple, normalize=lambda x: x.lower())
    shortnamestuple = (
        "v", "o", "s", "i", "u", "e", "p", "c", "b", "t", "z", "k", "a", "m")
    shortnamesenum = _util.Enum(
        shortnamestuple, normalize=lambda x: x.lower())

    shorttolongmap = dict(zip(shortnamestuple, longnamestuple))
    longtoshortmap = dict(zip(longnamestuple, shortnamestuple))

    def ConvertShortToLongDesc(cls, shortdesc):
        if shortdesc in cls.longnamesenum:
            return cls.longnames.normalize(shortdesc)

        if shortdesc not in cls.shortnamesenum:
            raise SDPNoSuchDescription(
                "No such description: {0}".format(shortdesc))

        return cls.shorttolongmap[cls.shortnamesenum.normalize(shortdesc)]

    def ConvertLongToShortDesc(cls, longdesc):
        if longdesc in cls.shortnamesenum:
            return cls.longnamesenum.normalize(longdesc)

        if longdesc not in cls.longnamesenum:
            raise SDPNoSuchDescription(
                "No such description: {0}".format(longdesc))

        return cls.longtoshortmap[cls.longnamesenum.normalize(longdesc)]

    descvalpattern = (
        "([^{eol}]+)[{eol}]+".format(eol=prot.EOL)
    )

    tdescpattern = (
        "t={valpat}"
        "((r={valpat})*)"  # May be one or more repeats.
        "".format(valpat=descvalpattern)
    )
    mdescpattern = (
        "m={valpat}"
        "(i={valpat})?"
        "(c={valpat})?"
        "(b={valpat})?"
        "(k={valpat})?"
        "((a={valpat})*)"
        "".format(valpat=descvalpattern)
    )

    parseinfo = {
        Parser.Pattern:
            # Each valpat has a single group in it, which covers the value of
            # the line.
            "v={valpat}"
            "o={valpat}"
            "s={valpat}"
            "(i={valpat})?"  # Optional info line.
            "(u={valpat})?"
            "(e={valpat})?"
            "(p={valpat})?"
            "(c={valpat})?"
            "(b={valpat})?"
            "(({td})+)"  # There may be one or more time descriptions.
            "(z={valpat})?"  # Timezone
            "(k={valpat})?"  # Encryption key
            "((a={valpat})*)"  # Zero or more attributes.
            "(({md})*)"  # Zero or more media descriptions.
            "".format(
                valpat=descvalpattern, td=tdescpattern, md=mdescpattern),
        Parser.Mappings:
            [("version", int),
             ("owner",),
             ("sessionname",),
             None, ("info",),
             None, ("uri",),
             None, ("email",),
             None, ("phone",),
             None, ("connectioninfo",),
             None, ("bandwidthinfo",),
             None, None, ("times",), None, None, None,
             ("timezone",),
             ("encryptionkey",),
             ("attributes",), None, None,
             ("medias",)]
    }

    def __str__(self):

        all_lines = []
        for reqdsess in ("version", "owner", "sessionname"):
            all_lines.append(
                "{0}={1}".format(
                    self.ConvertLongToShortDesc(reqdsess),
                    str(getattr(self, reqdsess))))

        for perhaps_sess in ("info", "uri"):
            if hasattr(self, perhaps_sess):
                all_lines.append(
                    "{0}={1}".format(
                        self.ConvertLongToShortDesc(perhaps_sess),
                        str(getattr(self, perhaps_sess))))

        all_lines.append("{0}={1}".format(
            self.ConvertLongToShortDesc("time"), str(self.times)))
        all_lines.append("")
        return prot.EOL.join(all_lines)


class SDPLine(object):
    types = _util.Enum(
        ("v", "o", "s", "i", "u", "e", "p", "c", "b", "z", "k", "a", "m"),
        normalize=lambda x: x.lower())
