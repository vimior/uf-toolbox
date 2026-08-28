# -*- coding: utf-8 -*-
"""本地意图识别 — 无参数启动/停止类指令 (打开插件/启动外部工具), 零 token。

只做词法提取 (动词 + 目标串), 不做名称匹配 — 置信门复用工具自身的
resolver (plugins_operation/tools_operation 均是"精确 → 唯一模糊"分级,
失败返回 error 且无副作用), 未命中由调用方静默交 LLM。

覆盖形态: [礼貌前缀] 动词 目标 [助词], 多目标用 、和,and 等分隔;
提问形态 ("X怎么打开") 拒绝 — 那是询问不是指令。
"""
import re

# 动词分组 → plugins_operation action (外部工具仅 start 有对应 launch)
_VERB_GROUPS = (
    ('start', ('打开', '启动', '开一下', '开',
               'open', 'launch', 'start', 'run')),
    ('stop', ('关闭', '关掉', '停止', '停掉', '停', '关了',
              'close', 'stop', 'quit', 'exit')),
)
# 数量分组, 忽略
_QUANTITIES = ('一', '二', '两', '俩', '三', '四', '五', '六', '七', '八', '九', '十', 
               '1', '2', '3', '4', '5', '6', '7', '8', '9', '10')
# 量词分组, 忽略
_QUANTIFIERS = ('个')
# 礼貌/请求前缀 (迭代剥除; 长前缀优先)
_PREFIXES = ('你可不可以', '你能不能', '你可以', '请帮我', '可不可以',
             '能不能', '帮我', '麻烦你', '麻烦', '我想', '我要', '请',
             '给我', '你能', '小u小u', '小u',
             'could you please', 'could you', 'can you', 'please')
# 尾部语气助词 (迭代剥除)
_SUFFIXES = ('一下', '吧', '呢', '啊', '呀', '哈')
# 提问形态 — 出现即拒绝 (询问方法而非指令)
_QUESTION_HINTS = ('怎么', '怎样', '如何', '为什么', '为何',
                   '吗', '嘛', 'how to', 'why', 'what')
# 多目标分隔
_SEPS = re.compile(r'[、，,；;]|\s+and\s+|\s*&\s*|和|与|跟|以及')
# 句首尾标点
_PUNCT = ' \t\r\n!?！?。.~～'


def _strip_prefixes(s):
    """迭代剥礼貌前缀 (中文直接前缀匹配; 英文按词边界)."""
    changed = True
    while changed:
        changed = False
        low = s.lower()
        for p in _PREFIXES:
            if not low.startswith(p):
                continue
            rest = s[len(p):]
            # 英文前缀后必须是词边界 (防 "open" 误剥 "opener"...)
            if p[0].isascii() and rest[:1].isalpha():
                continue
            s = rest.lstrip(_PUNCT)
            changed = True
            break
    return s


def extract_open(question):
    """识别"打开/关闭 X"指令 → (action, targets) 或 None.

    action: 'start' | 'stop' (plugins_operation 的 action;
    外部工具仅 start 有对应 launch)。targets 保留原文大小写,
    交给工具 resolver 自行归一化匹配。
    """
    if not isinstance(question, str):
        return None
    q = question.strip(_PUNCT)
    if not q:
        return None
    low = q.lower()
    if any(h in low for h in _QUESTION_HINTS):
        return None
    q = _strip_prefixes(q)
    low = q.lower()
    action, target = None, None
    for act, verbs in _VERB_GROUPS:
        for v in verbs:
            if not low.startswith(v):
                continue
            rest = q[len(v):]
            # 忽略数量词
            for q in _QUANTITIES:
                if rest.startswith(q):
                    rest = rest[len(q):]
            # 忽略量词
            for q in _QUANTIFIERS:
                if rest.startswith(q):
                    rest = rest[len(q):]
            # 英文动词后必须词边界 ("running" ≠ run + ning)
            if v[0].isascii() and rest[:1].isalpha():
                continue
            action, target = act, rest
            break
        if action:
            break
    if not action or target is None:
        return None
    target = target.strip(_PUNCT)
    # 迭代剥尾部助词
    changed = True
    while changed:
        changed = False
        for sfx in _SUFFIXES:
            if target.endswith(sfx):
                target = target[:-len(sfx)].rstrip(_PUNCT)
                changed = True
                break
    if not target:
        return None
    targets = [t.strip(_PUNCT) for t in _SEPS.split(target)]
    targets = [t for t in targets if t]
    if not targets:
        return None
    return action, targets
