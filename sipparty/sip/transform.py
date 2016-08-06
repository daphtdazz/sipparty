"""transform.py

Routines to do tranformations of SIP messages.

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
from numbers import Integral
from ..util import Enum

log = logging.getLogger(__name__)

TransformKeys = Enum(("Copy", "Add", "CopyFrom"))
Tfk = TransformKeys


def raiseActTupleError(tp, msg):
    raise ValueError(
        "Transform action tuple is unrecognisable: %s" % (tp, msg))


def Transform(tform_dict, inobj, intype, outobj, outtype, **sources):
    tform = LookupTransform(tform_dict, intype, outtype)
    for actTp in tform:
        action = actTp[0]

        if action not in Tfk:
            raiseActTupleError(actTp, "Unrecognised action %r." % action)

        if action == Tfk.Copy:
            if len(actTp) < 2:
                raiseActTupleError(actTp, "No path to copy.")
            path = actTp[1]
            log.debug('copy %s', path)
            val = inobj.attributeAtPath(path)
            outobj.setAttributePath(path, val)
            continue

        if action == Tfk.Add:
            if len(actTp) < 3:
                raiseActTupleError(actTp, "No generator for Add action.")
            path = actTp[1]
            log.debug('generate %s', path)
            gen = actTp[2]
            outobj.setAttributePath(path, gen(inobj))
            continue

        if action == Tfk.CopyFrom:
            if len(actTp) < 3:
                raiseActTupleError(
                    actTp, "No attribute specified to %r action." % (
                        Tfk.CopyFrom,))
            source = actTp[1]
            if source not in sources:
                raiseActTupleError(
                    actTp, "Source %r not passed into %r action." % (
                        source, Tfk.CopyFrom))
            path = actTp[2]
            log.debug('copy from source %s to %s', source, path)
            tobj = sources[source]
            val = tobj.attributeAtPath(path)
            outobj.setAttributePath(path, val)
            continue
        raise ValueError('Unrecognised action %r' % (action,))


def LookupTransform(transforms, qutype, anstype):

    answers_dict = _FindTypeDict(transforms, qutype)
    answer_tform = _FindTypeDict(answers_dict, anstype)
    return answer_tform


def _FindTypeDict(dicts, typ):

    if isinstance(typ, Integral):
        while typ > 0:
            if typ in dicts:
                rdict = dicts[typ]
                return rdict
            typ /= 10
        else:
            raise KeyError(
                "Transform dictionary %r does not contain type %r" % (
                    dicts, typ))

    if typ not in dicts:
        raise KeyError(
            '%r transform type not in transforms %r' % (typ, dicts))
    return dicts[typ]
