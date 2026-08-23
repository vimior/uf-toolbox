# -*- coding: utf-8 -*-
"""内置基础问答 — 本地应答, 不走 LLM (离线可用, 零 token 消耗).

三层匹配, 按优先级:
1. 精确唤醒层 — 归一化后整串相等 (dict 查找)。必须精确: 子串匹配
   "小u" 会把 "小U帮我打开任务调度器" 这类真实指令吞掉;
2. 关键词子串层 — 身份/打造者/能力, 命中关键词即答;
3. 模糊层 — difflib 相似度 ≥0.7 且 4≤长度≤20: 容错"你到底是谁"
   这类插入词; 长度上限防长句真实请求被劫持 (应走 LLM)。

问题归一化: 去空白/标点/小写。
"""
import re
from difflib import SequenceMatcher

_NORM = re.compile(r'[\s\W_]+', re.UNICODE)

# ---- 层 1: 精确唤醒 (归一化串 → 答案键; 中英输入共用一张表, 答案随问句语言) ----
_EXACT_RULES = {
    '小u': 'wake', '小u小u': 'wake2', '小u在吗': 'present',
    '你好': 'hello', '您好': 'hello', '嗨': 'hello', '喂': 'hello', '哈喽': 'hello',
    'hi': 'hello', 'hello': 'hello', 'hey': 'hello', 'halo': 'hello',
    '在吗': 'present', '在不在': 'present', '在么': 'present', '在': 'wake',
    '谢谢': 'thanks', '谢谢你': 'thanks', '谢谢您': 'thanks',
    '多谢': 'thanks', '感谢': 'thanks', 'thanks': 'thanks',
    'thankyou': 'thanks', 'thx': 'thanks',
    '再见': 'bye', '拜拜': 'bye', '拜': 'bye',
    'bye': 'bye', 'goodbye': 'bye', 'seeyou': 'bye',
}

# ---- 层 2: 关键词子串 (命中即答) — 关键词为归一化形式 ----
_QA_RULES = [
    (('你是谁', '你叫什么', '你是哪位', '你的名字',
      'whoareyou', 'whatareyou', 'whatsyourname', 'whatisyourname'),
     'identity'),
    (('你由谁打造', '谁打造了你', '谁开发的你', '谁创造了你', '谁做的你',
      '你的开发者', 'whomadeyou', 'whocreatedyou', 'whodevelopedyou'),
     'creator'),
    (('你会什么', '你会做什么', '你能做什么', '你能干什么', '你会干啥',
      '你有什么能力', '你有什么技能', '你的能力', '你的技能', '你会哪些',
      'whatcanyoudo', 'yourskills', 'yourabilities'),
     'skills'),
]

# ---- 层 3: 模糊 (canonical 问式, 模块加载时归一化) ----
_FUZZY_MIN_LEN = 4    # 过短串相似度噪声大
_FUZZY_MAX_LEN = 20   # 长句必是真实请求, 防劫持 LLM 流程
_FUZZY_THRESHOLD = 0.7
_FUZZY_FORMS = [
    (('你是谁', '你叫什么', 'who are you', 'what is your name'), 'identity'),
    (('你由谁打造', '谁开发的你', 'who made you', 'who created you'), 'creator'),
    (('你会什么', '你会做什么', '你能做什么', '你有什么能力',
      'what can you do'), 'skills'),
]

_ANSWERS_ZH = {
    'wake': '我在呢',
    'wake2': '我在呢，有什么可以帮到您？',
    'present': '我在呢，有什么可以帮你？',
    'hello': '你好！我是小U，有什么可以帮你？',
    'thanks': '不客气！',
    'bye': '再见！有需要随时叫我。',
    'identity': ('我是小U，UFToolBox 的内置智能助手，由大语言模型驱动。'
                 '我可以为你：打开插件/启动外部工具、发送系统通知、创建定时任务。'),
    'creator': '我由 Dwen 打造，是 UFToolBox 的内置智能助手。',
    'skills': ('我可以：\n'
               '- 打开/关闭/隐藏 应用的插件\n'
               '- 启动外部工具、发送系统通知、创建定时任务\n'
               '- 调用其他插件注册的扩展能力\n'
               '当前可用工具: %s'),
}

_ANSWERS_EN = {
    'wake': "I'm here",
    'wake2': "I'm here — how can I help?",
    'present': "I'm here. What can I do for you?",
    'hello': "Hi! I'm U-Bot. How can I help?",
    'thanks': "You're welcome!",
    'bye': 'Bye! Call me anytime you need.',
    'identity': ("I'm U-Bot, the built-in smart assistant of UFToolBox, "
                 "powered by an LLM. I can open plugins and external tools, "
                 "send notifications, schedule tasks."),
    'creator': ('I am built by Dwen as the built-in smart assistant of UFToolBox.'),
    'skills': ('I can:\n'
               '- open/close/hide plugins\n'
               '- launch external tools, send notifications, schedule tasks\n'
               '- call capabilities registered by other plugins\n'
               'Available tools: %s'),
}


def _norm(q):
    return _NORM.sub('', str(q)).lower()


def _is_zh(text):
    return any('一' <= ch <= '鿿' for ch in str(text))


_FUZZY_RULES = [(tuple(_norm(f) for f in forms), key)
                for forms, key in _FUZZY_FORMS]


def _render(key, zh, tool_names):
    ans = (_ANSWERS_ZH if zh else _ANSWERS_EN)[key]
    if '%s' in ans:
        ans = ans % ', '.join(tool_names or ['(无)' if zh else '(none)'])
    return ans


def match_basic_qa(question, tool_names=None):
    """匹配内置问答 — 命中返回答案文本, 否则 None.

    *tool_names*: 工具名列表, 注入"你会什么"的答案 (可空)。
    """
    q = _norm(question)
    if not q:
        return None
    zh = _is_zh(question)
    key = _EXACT_RULES.get(q)                    # 层 1: 精确唤醒
    if key:
        return _render(key, zh, tool_names)
    for keywords, key in _QA_RULES:              # 层 2: 关键词子串
        if any(k in q for k in keywords):
            return _render(key, zh, tool_names)
    if _FUZZY_MIN_LEN <= len(q) <= _FUZZY_MAX_LEN:   # 层 3: 模糊
        best, score = None, _FUZZY_THRESHOLD
        for forms, key in _FUZZY_RULES:
            for f in forms:
                r = SequenceMatcher(None, q, f).ratio()
                if r > score:
                    best, score = key, r
        if best:
            return _render(best, zh, tool_names)
    return None
