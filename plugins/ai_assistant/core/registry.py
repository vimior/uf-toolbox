# -*- coding: utf-8 -*-
"""Tool registry — ToolRegistry 类 + 全局单例 + 装饰器注册.

工具 entry: {'name', 'description', 'dangerous', 'schema', 'fn'|'fn_ref',
             'summary'?} — schema 为 OpenAI function-calling 格式。

- fn(args_dict) 在 agent 工作线程执行: 必须线程安全、无 UI;
- fn_ref: 'ns@method', 由服务经 services.call(ref, **args) 执行, 任何
  插件都可借此贡献能力 (同 task scheduler 的 fn_ref 约定);
- summary(result, args) -> str|None: 面板一行摘要, 仅 fn 工具可携带。

三种注册方式:
1. registry.register(name, desc, schema, fn=.../fn_ref=...)
   方法注册 — schema 直接给 OpenAI 格式;
   省略 schema 且给定 fn 时从函数签名自动生成 (fn 按 fn(**kwargs)
   约定编写, 内部经 wrap_kwargs 适配; name 省略取 fn.__name__);
2. @registry.tool(...)
   装饰器 — 省略 schema 时同 1 的自动推导;
3. @tool_spec(...) + register_tools_from(registry, instance)
   类方法批量注册 — 实例化时扫描绑定 (见 tools/file_ops.py)。
"""
import threading

from .schema import schema_from_function, wrap_kwargs


class ToolRegistry:
    """工具注册表 — 按 name 幂等; 注册/遍历加锁 (服务/工作线程并发)."""

    def __init__(self):
        self._tools = {}
        self._order = []
        self._lock = threading.Lock()

    def register(self, name=None, description=None, schema=None, fn=None,
                 fn_ref=None, dangerous=False, summary=None):
        """注册 (或替换) 工具. fn 与 fn_ref 必给其一.

        省略 schema 且给定 fn: 从函数签名 (类型注解/docstring) 自动
        生成 OpenAI schema, 函数按 fn(**kwargs) 约定编写 (内部经
        wrap_kwargs 适配为 fn(args_dict)); fn_ref 工具必须显式给
        name 与 schema。
        """
        if fn is None and not fn_ref:
            raise ValueError('tool %r needs fn or fn_ref' % name)
        if name is None:
            if fn is None:
                raise ValueError('fn_ref tool needs explicit name')
            name = fn.__name__
        if schema is None:
            if fn is None:
                raise ValueError('fn_ref tool %r needs explicit schema' % name)
            schema = schema_from_function(fn, name=name,
                                          description=description)
            fn = wrap_kwargs(fn)
        if description is None:
            description = schema['function'].get('description', '')
        entry = {'name': name, 'description': description,
                 'schema': schema, 'dangerous': dangerous}
        if fn is not None:
            entry['fn'] = fn
            if callable(summary):
                entry['summary'] = summary
        else:
            entry['fn_ref'] = fn_ref
        with self._lock:
            self._tools[name] = entry
            if name not in self._order:
                self._order.append(name)
        return entry

    def tool(self, name=None, description=None, schema=None,
             dangerous=False, summary=None):
        """装饰器注册 fn 工具.

        省略 schema: 从函数签名 (类型注解/docstring) 生成 OpenAI
        schema, 函数按 fn(**kwargs) 编写;
        显式 schema: 函数沿用 fn(args_dict) 约定。
        """
        def deco(func):
            self.register(name, description, schema, fn=func,
                          dangerous=dangerous, summary=summary)
            return func
        return deco

    def unregister(self, name):
        with self._lock:
            self._tools.pop(name, None)
            if name in self._order:
                self._order.remove(name)

    def get(self, name):
        with self._lock:
            return self._tools.get(name)

    def list_tools(self):
        """按注册序返回 entry 拷贝 — 遍历时注册不抛错."""
        with self._lock:
            return [self._tools[n] for n in self._order if n in self._tools]


registry = ToolRegistry()   # 全局单例 — 服务/内置工具/声明式工具共用


def tool_spec(name=None, description=None, dangerous=False, summary=None):
    """标记类方法为工具 (仅贴元数据) — 由 register_tools_from 扫描注册."""
    def deco(func):
        func._tool_spec = {'name': name, 'description': description,
                           'dangerous': dangerous, 'summary': summary}
        return func
    return deco


def register_tools_from(reg, instance):
    """把 instance 上被 @tool_spec 标记的绑定方法注册进 reg.

    按类定义顺序注册 (dir() 是字母序, 遍历 mro 的 __dict__ 保持源码序)。
    """
    seen = set()
    for klass in reversed(type(instance).__mro__):
        for attr in vars(klass).values():
            spec = getattr(attr, '_tool_spec', None)
            if spec is None:
                continue
            name = spec['name'] or attr.__name__
            if name in seen:    # 子类覆盖同名方法时只注册一次
                continue
            seen.add(name)
            reg.tool(**spec)(getattr(instance, attr.__name__))
