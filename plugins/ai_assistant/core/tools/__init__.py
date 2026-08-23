# -*- coding: utf-8 -*-
"""内置工具包 — register_builtin 显式注册入口 (无 import 副作用)."""
from . import network, system_info
from .file_ops import FileTools


def register_builtin(registry):
    """把全部内置工具注册进给定注册表 (幂等, 按 name 覆盖)."""
    FileTools(registry)
    network.register(registry)
    system_info.register(registry)
