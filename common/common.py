# -*- coding: utf-8 -*-
"""Shared constants and logger."""
import logging
import os
import sys

__version__ = '1.0.0'

if sys.platform == 'win32':
    FONT_FAMILY = 'Microsoft YaHei'
    MONO_FAMILY = 'Consolas'
elif sys.platform == 'darwin':
    FONT_FAMILY = 'PingFang SC'
    MONO_FAMILY = 'Menlo'
else:
    FONT_FAMILY = 'Ubuntu'
    MONO_FAMILY = 'DejaVu Sans Mono'

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

LOG_FMT = '[%(levelname)s][%(asctime)s] - - %(message)s'
LOG_DATE_FMT = '%Y-%m-%d %H:%M:%S'
logger = logging.getLogger('uf.toolbox')
logger.setLevel(logging.INFO)
logger.addHandler(logging.NullHandler())
