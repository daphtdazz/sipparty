"""__init__.py

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
from six import itervalues
from ..dialog import Dialog
from .call import (SimpleCallDialog,)

AllDialogsTypes = [
    dlg for dlg in itervalues(dict(locals()))
    if isinstance(dlg, type) and issubclass(dlg, Dialog) and dlg is not Dialog]
del Dialog
del itervalues
