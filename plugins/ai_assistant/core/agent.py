# -*- coding: utf-8 -*-
"""Tool-calling agent loop — model-agnostic (any OpenAI-compatible client).

UI-independent: runs on a worker thread, communicates via a generator of
events; the caller (service) forwards them to the UI on the main thread.
"""
import json
import time


class Agent:
    """Single-question agent loop with tool calls and a confirm hook."""

    MAX_ROUNDS = 10   # 工具调用轮数上限, 防模型死循环
    TOOL_RESULT_MAX = 6000   # 回填模型的单条工具结果上限; session 存盘
                             # 不再二次截断 (模型所见即所存, 防历史倒挂)

    def __init__(self, client, tools, confirm_cb=None):
        """tools: list of dicts with keys name/schema/dangerous/fn.

        confirm_cb(name, args) -> bool is called (blocking) before a
        dangerous tool executes; False = user rejected.
        """
        self.client = client
        self._tools = {t['name']: t for t in tools}
        self.confirm_cb = confirm_cb

    def schemas(self):
        """OpenAI-compatible tool schemas for the API request."""
        return [t['schema'] for t in self._tools.values() if t.get('schema')]

    def run(self, messages, stop_event=None):
        """Generator of events, one tuple per step:

        ('text', str)                    流式文本增量
        ('progress', phase, round_no)    阶段进展 (phase='request': 发起第 N 轮请求)
        ('timing', kind, label, secs)    耗时上报 (kind='request'/'tool',
                                         label=轮次或工具名)
        ('tool_call', name, args_dict)   工具执行开始
        ('tool_result', name, result)    工具结果
        ('done', text_or_None, usage)   本轮结束 (text = 最终回复全文;
                                         usage = 累计 token 用量 dict 或 None)

        注意: 工具交换消息 (assistant tool_calls / tool) 原地回填进 messages
        — 调用方可在结束后截取新增段写回会话历史, 让多轮模型看到完整的
        工具调用过程 (否则历史只有"问→直接答", 模型会学着不调工具编结果)。
        """
        msgs = messages   # 原地回填 — 见 docstring
        total_usage = {}   # 多轮工具调用时逐请求累加
        for round_no in range(1, self.MAX_ROUNDS + 1):
            if stop_event is not None and stop_event.is_set():
                yield ('done', None, total_usage or None)
                return
            yield ('progress', 'request', round_no)
            if stop_event is not None and stop_event.is_set():
                yield ('done', None, total_usage or None)
                return
            acc = {}          # index -> {id, name, arguments} 增量累积
            full_text = ''
            t0 = time.monotonic()
            t_first = None    # 首 token 到达时刻 (TTFT 统计)
            for delta_text, deltas in self.client.chat_stream(msgs,
                                                              self.schemas()):
                if stop_event is not None and stop_event.is_set():
                    yield ('done', None, total_usage or None)
                    return
                if t_first is None and (delta_text or deltas):
                    t_first = time.monotonic()
                if delta_text:
                    full_text += delta_text
                    yield ('text', delta_text)
                for d in deltas:
                    slot = acc.setdefault(d['index'],
                                          {'id': '', 'name': '',
                                           'arguments': ''})
                    if d['id']:
                        slot['id'] = d['id']
                    if d['name']:
                        slot['name'] += d['name']
                    if d['arguments']:
                        slot['arguments'] += d['arguments']
            if t_first is not None:
                yield ('timing', 'ttft', round_no, t_first - t0)
            yield ('timing', 'request', round_no, time.monotonic() - t0)
            self._accum_usage(total_usage)
            if not acc:
                yield ('done', full_text, total_usage or None)
                return
            # assistant 消息 (含 tool_calls) 回填
            msgs.append({'role': 'assistant', 'content': full_text or None,
                         'tool_calls': [
                             {'id': s['id'], 'type': 'function',
                              'function': {'name': s['name'],
                                           'arguments': s['arguments']}}
                             for s in acc.values()]})
            for s in acc.values():
                if stop_event is not None and stop_event.is_set():
                    yield ('done', None, total_usage or None)
                    return
                name = s['name']
                tool = self._tools.get(name)
                try:
                    args = json.loads(s['arguments'] or '{}')
                except ValueError:
                    args = None
                if tool is None:
                    result = 'unknown tool: %s' % name
                elif args is None:
                    result = 'invalid arguments json'
                else:
                    yield ('tool_call', name, args)
                    if (tool.get('dangerous') and self.confirm_cb is not None
                            and not self.confirm_cb(name, args)):
                        result = 'user rejected'
                    else:
                        t1 = time.monotonic()
                        try:
                            result = tool['fn'](args)
                        except Exception as e:
                            result = 'error: %s' % e
                        yield ('timing', 'tool', name, time.monotonic() - t1)
                result_str = str(result)
                yield ('tool_result', name, result_str)
                if len(result_str) > self.TOOL_RESULT_MAX:
                    result_str = (result_str[:self.TOOL_RESULT_MAX]
                                  + '… (结果过长已截断)')
                msgs.append({'role': 'tool', 'tool_call_id': s['id'],
                             'content': result_str})
        yield ('done', None, total_usage or None)

    def _accum_usage(self, total):
        """把客户端最近一次请求的 usage 累加进 total (按键相加)."""
        usage = getattr(self.client, 'last_usage', None)
        if not isinstance(usage, dict):
            return
        for k, v in usage.items():
            if isinstance(v, (int, float)):
                total[k] = total.get(k, 0) + v
