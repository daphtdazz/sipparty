"""splogging.py

Utility functions for py-sip.

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
import logging.config
import os

assert logging.DEBUG == 10
logging.DETAIL = 5
logging.addLevelName(logging.DETAIL, "DETAIL")


class SPLogger(logging.getLoggerClass()):

    global_debug_logs_enabled = True 
    global_detail_logs_enabled = False

    def debug(self, msg, *args, **kwargs):
        if not self.global_debug_logs_enabled:
            return
        return super(SPLogger, self).debug(msg, *args, **kwargs)

    def detail(self, msg, *args, **kwargs):
        if not self.global_detail_logs_enabled:
            return
        self.log(logging.DETAIL, msg, *args, **kwargs)

logging.setLoggerClass(SPLogger)

LOGGING_CONF_FILE = '.sipparty_logging.conf'

if False and os.path.exists(LOGGING_CONF_FILE):
    logging.config.fileConfig(LOGGING_CONF_FILE)
