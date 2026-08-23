# -*- coding: utf-8 -*-
"""OpenAI function-calling schema 统一创建入口.

三种形态 (输出均为 OpenAI 格式 {'type':'function','function':{...}}):
- function_schema: 直接拼 properties/required (完全手写)
- make_schema: 四元组 (name, type, description, required) 声明式
  (插件 agent_tools AST 声明沿用此入口)
- schema_from_function: 从函数签名 (类型注解 + docstring) 自动推导,
  配合 wrap_kwargs 使工具函数可按 fn(**kwargs) 约定编写
"""
import inspect
import re
from typing import Literal, get_args, get_origin

_TYPE_MAP = {str: 'string', int: 'integer', float: 'number',
             bool: 'boolean', list: 'array', dict: 'object'}
# docstring 参数行: "path: 文件路径" / "path：文件路径"
_PARAM_DOC = re.compile(r'^(\w+)\s*[:：]\s*(.+)$')


def function_schema(name, description, props, required):
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': props,
                'required': required
            }
        }
    }


def make_schema(name, description, params):
    """能力声明 → OpenAI schema. 每个参数两种形态:

    - 四元组 (name, type, description?, required?) — 简洁声明, 沿用至今;
    - dict {'name', 'type', 'description'?, 'required'?, **extra} —
      extra 原样透传进 property (enum/default/items/pattern 等
      OpenAI 支持的全部字段, 四元组形态表达不了时用这种)。
    """
    props = {}
    required = []
    for item in params or []:
        if isinstance(item, dict):
            pname = str(item.get('name', ''))
            if not pname:
                continue
            prop = {'type': str(item.get('type', 'string'))}
            if item.get('description'):
                prop['description'] = str(item['description'])
            for k, v in item.items():
                if k not in ('name', 'type', 'description', 'required'):
                    prop[k] = v       # enum/default/items/pattern... 透传
            props[pname] = prop
            if item.get('required'):
                required.append(pname)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            pname = str(item[0])
            ptype = str(item[1])
            pdesc = str(item[2]) if len(item) > 2 else ''
            props[pname] = {'type': ptype, 'description': pdesc}
            if len(item) > 3 and item[3]:
                required.append(pname)
    return function_schema(name, description, props, required)


def schema_from_function(fn, name=None, description=None):
    """从函数签名推导 OpenAI schema.

    类型注解 → 参数类型 (无注解按 string); 无默认值 → required;
    Literal['a', 'b'] 注解 → enum 约束; docstring 首行 → 工具描述,
    后续 "param: 描述" 行 → 参数描述。
    """
    doc = inspect.getdoc(fn) or ''
    lines = doc.splitlines()
    desc = description if description is not None else (
        lines[0] if lines else '')
    param_docs = {}
    for line in lines[1:]:
        m = _PARAM_DOC.match(line.strip())
        if m:
            param_docs[m.group(1)] = m.group(2).strip()
    props = {}
    required = []
    for pname, p in inspect.signature(fn).parameters.items():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL,
                      inspect.Parameter.VAR_KEYWORD):
            continue
        ann = p.annotation
        if get_origin(ann) is Literal:
            # Literal['a', 'b'] → enum 硬约束 (类型取第一个枚举值)
            vals = list(get_args(ann))
            prop = {'type': _TYPE_MAP.get(type(vals[0]), 'string'),
                    'enum': vals} if vals else {'type': 'string'}
        else:
            prop = {'type': _TYPE_MAP.get(ann, 'string')}
        if pname in param_docs:
            prop['description'] = param_docs[pname]
        props[pname] = prop
        if p.default is inspect.Parameter.empty:
            required.append(pname)
    return function_schema(name or fn.__name__, desc, props, required)


def wrap_kwargs(fn):
    """fn(**kwargs) → fn(args_dict) 适配器 — 过滤签名外的多余键.

    模型给的 arguments 是整体字典; 拆包调用让工具函数保持正常的
    Python 签名, 多余键 (弱模型常见) 被丢弃而非 TypeError。
    """
    params = inspect.signature(fn).parameters
    accepts_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD
                         for p in params.values())

    def wrapper(args):
        if accepts_var_kw:
            return fn(**args)
        known = {k: v for k, v in args.items() if k in params}
        return fn(**known)
    return wrapper
