# -*- coding: utf-8 -*-
"""小U — 交互面板插件 (loader 经 dir() 发现 AgentPanel).

AgentService 服务类在本包内但不导出: 由 manager 的
BUILTIN_SERVICES 内置启动 (同 task_service 机制), 不占用插件菜单.
"""
from .agent_panel import AgentPanel  # noqa: F401
