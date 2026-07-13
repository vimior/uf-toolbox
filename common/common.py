# -*- coding: utf-8 -*-
"""Shared constants and logger."""
import logging
import os
import sys

if sys.platform == 'win32':
    FONT_FAMILY = 'Microsoft YaHei'
elif sys.platform == 'darwin':
    FONT_FAMILY = 'PingFang SC'
else:
    FONT_FAMILY = 'Ubuntu'

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

LOG_FMT = '[%(levelname)s][%(asctime)s] - - %(message)s'
LOG_DATE_FMT = '%Y-%m-%d %H:%M:%S'
_logger = logging.getLogger('uf.toolbox')
_logger.setLevel(logging.INFO)
_logger.addHandler(logging.NullHandler())


def get_logger():
    return _logger
