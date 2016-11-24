"""logging.py

Setup for the sip party logging code.

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
from __future__ import absolute_import

from logging.config import dictConfig

default_logging_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'console': {
            'format':
                '%(levelname)s +%(relativeCreated)d %(name)s.%(lineno)d: '
                '%(message)s'
        },
    },
    'handlers': {
        'console': {
            # NB: for performance global debug logs are disabled by default
            # in sipparty.logging, so you will need to enable them there as
            # well if you want to turn this up.
            'level': 'WARNING',
            'formatter': 'console',
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING'
    },
    'loggers': {
        'sipparty.test': {
            'level': 'INFO'
        },
    }
}

dictConfig(default_logging_config)
