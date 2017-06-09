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
# Need to import logging before anything else.
from . import logging
# need to patch threading on python2
from six import PY2
import threading

if PY2:
    if threading.active_count() > 1:
        raise Exception(
            'sipparty needs to be imported on the main thread in python2 so '
            'that it can deduce the main thread.')
    mthr = threading.current_thread()
    def main_thread():
        return mthr
    threading.main_thread = main_thread
