# -*- coding: utf-8 -*-
"""Unit tests for local intent (zero-token open/close commands)."""
import json
import threading
import unittest
from unittest.mock import MagicMock

from plugins.ai_assistant.core.local_intent import extract_open
from plugins.ai_assistant.core.registry import registry


class TestExtractOpen(unittest.TestCase):
    """词法提取: 动词 + 目标, 提问形态拒绝."""

    def test_basic_zh(self):
        self.assertEqual(extract_open('打开任务调度器'),
                         ('start', ['任务调度器']))

    def test_polite_prefix(self):
        self.assertEqual(extract_open('帮我打开任务调度器'),
                         ('start', ['任务调度器']))
        self.assertEqual(extract_open('请打开任务调度器'),
                         ('start', ['任务调度器']))
        self.assertEqual(extract_open('小U帮我打开任务调度器'),
                         ('start', ['任务调度器']))

    def test_suffix_particles(self):
        self.assertEqual(extract_open('打开任务调度器一下吧'),
                         ('start', ['任务调度器']))

    def test_close_verbs(self):
        self.assertEqual(extract_open('关闭任务调度器'), ('stop', ['任务调度器']))
        self.assertEqual(extract_open('关掉任务调度器'), ('stop', ['任务调度器']))
        # 把字句 (动词在句尾) v1 不支持 — 交 LLM
        self.assertIsNone(extract_open('帮我把任务调度器关掉'))

    def test_multi_targets(self):
        self.assertEqual(extract_open('打开任务调度和插件商店'),
                         ('start', ['任务调度', '插件商店']))
        self.assertEqual(extract_open('打开任务调度、插件商店'),
                         ('start', ['任务调度', '插件商店']))
        self.assertEqual(extract_open('打开任务调度，插件商店'),
                         ('start', ['任务调度', '插件商店']))

    def test_english(self):
        self.assertEqual(extract_open('open task panel'),
                         ('start', ['task panel']))
        self.assertEqual(extract_open('please open task panel'),
                         ('start', ['task panel']))

    def test_english_verb_word_boundary(self):
        """running 不应被 run 动词误剥."""
        self.assertIsNone(extract_open('running 是什么意思'))

    def test_question_form_rejected(self):
        self.assertIsNone(extract_open('任务调度器怎么打开'))
        self.assertIsNone(extract_open('如何打开任务调度器'))
        self.assertIsNone(extract_open('为什么打不开任务调度器'))

    def test_no_target(self):
        self.assertIsNone(extract_open('打开'))
        self.assertIsNone(extract_open('帮我打开'))

    def test_not_open_intent(self):
        self.assertIsNone(extract_open('10分钟后提醒我喝水'))
        self.assertIsNone(extract_open('今天天气怎么样'))

    def test_punctuation_stripped(self):
        self.assertEqual(extract_open('打开任务调度器！'),
                         ('start', ['任务调度器']))


class TestLocalIntentService(unittest.TestCase):
    """服务层: 置信门复用 resolver, 未命中静默交 LLM."""

    def setUp(self):
        from plugins.ai_assistant.agent_service import AgentService
        self.calls = []

        def plugins_fn(action='', targets='', **_kw):
            self.calls.append(('plugins', {'action': action,
                                           'targets': targets}))
            if '任务调度' in targets:
                return {'task_panel': 'ok'}
            return 'error: 未匹配到插件'

        def tools_fn(action='', targets='', **_kw):
            self.calls.append(('tools', {'action': action,
                                         'targets': targets}))
            if targets == '终端':
                return {'终端': 'ok: 已启动 终端'}
            return {'不存在的东西': 'error: 未匹配到工具'}

        registry.register('plugins_operation', fn=plugins_fn)
        registry.register('tools_operation', fn=tools_fn)
        self.addCleanup(registry.unregister, 'plugins_operation')
        self.addCleanup(registry.unregister, 'tools_operation')

        svc = AgentService.__new__(AgentService)
        svc._session = []
        svc._session_id = 1          # _commit 需要当前会话 id
        svc._lock = threading.Lock()  # _commit 自锁
        svc._queue = MagicMock()
        svc._saved = []
        svc._save_session = lambda: svc._saved.append(True)
        self.svc = svc

    def _events(self):
        return [c.args[0] for c in self.svc._queue.put.call_args_list]

    def test_plugin_hit(self):
        ok = self.svc._try_local_intent(1, '打开任务调度', True)
        self.assertTrue(ok)
        kinds = [e[0] for e in self._events()]
        self.assertEqual(kinds, ['tool_call', 'tool_result', 'chunk', 'done'])
        done = self._events()[-1]
        self.assertEqual(done[3], 'local')   # 哨兵: 面板跳过 tokens/耗时
        # 写会话 (供后续"关掉它"指代)
        roles = [m['role'] for m in self.svc._session]
        self.assertEqual(roles, ['user', 'assistant'])
        self.assertTrue(self.svc._saved)

    def test_tool_fallback(self):
        ok = self.svc._try_local_intent(2, '打开终端', True)
        self.assertTrue(ok)
        self.assertEqual([c[0] for c in self.calls], ['plugins', 'tools'])
        ops = [e[2] for e in self._events() if e[0] == 'tool_call']
        self.assertEqual(ops, ['plugins_operation', 'tools_operation'])

    def test_miss_falls_to_llm(self):
        ok = self.svc._try_local_intent(3, '打开不存在的东西', True)
        self.assertFalse(ok)
        # 未命中也写入了失败回复会话
        roles = [m['role'] for m in self.svc._session]
        self.assertEqual(roles, ['user', 'assistant'])
        self.assertTrue(self.svc._saved)
        self.assertIn('无法打开', self.svc._session[-1]['content'])

    def test_stop_no_tool_fallback(self):
        ok = self.svc._try_local_intent(4, '关闭终端', True)
        self.assertFalse(ok)   # stop 无 tools 对应, 交 LLM

    def test_carry_false_no_session(self):
        ok = self.svc._try_local_intent(5, '打开任务调度', False)
        self.assertTrue(ok)
        self.assertEqual(self.svc._session, [])
        self.assertFalse(self.svc._saved)


if __name__ == '__main__':
    unittest.main()
