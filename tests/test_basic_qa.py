# -*- coding: utf-8 -*-
"""Unit tests for basic_qa local Q&A (zero-token answers)."""
import unittest

from plugins.ai_assistant.core.basic_qa import match_basic_qa


class TestExactWake(unittest.TestCase):
    """层 1: 精确唤醒 — 整串归一化后相等才命中."""

    def test_wake(self):
        self.assertEqual(match_basic_qa('小U'), '我在呢')

    def test_wake_punctuation(self):
        self.assertEqual(match_basic_qa('小U！'), '我在呢')

    def test_wake2(self):
        self.assertEqual(match_basic_qa('小U小U'), '我在呢，有什么可以帮到您？')

    def test_hello_zh(self):
        self.assertEqual(match_basic_qa('你好'), '你好！我是小U，有什么可以帮你？')

    def test_hello_en(self):
        self.assertEqual(match_basic_qa('hello'),
                         "Hi! I'm U-Bot. How can I help?")

    def test_present(self):
        self.assertEqual(match_basic_qa('在吗'), '我在呢，有什么可以帮你？')

    def test_thanks_zh(self):
        self.assertEqual(match_basic_qa('谢谢你'), '不客气！')

    def test_thanks_en(self):
        self.assertEqual(match_basic_qa('thanks'), "You're welcome!")

    def test_bye_zh(self):
        self.assertEqual(match_basic_qa('再见'), '再见！有需要随时叫我。')

    def test_wake_word_in_command_not_hijacked(self):
        """唤醒词嵌在真实指令里 → 不本地应答, 放行 LLM."""
        self.assertIsNone(match_basic_qa('小U帮我打开任务调度器'))
        self.assertIsNone(match_basic_qa('小U，10分钟后提醒我喝水'))


class TestKeywordRules(unittest.TestCase):
    """层 2: 关键词子串."""

    def test_identity(self):
        ans = match_basic_qa('你是谁')
        self.assertIn('小U', ans)
        self.assertIn('定时任务', ans)   # 身份答案含能力概述

    def test_identity_en(self):
        self.assertIn('U-Bot', match_basic_qa('who are you'))

    def test_creator(self):
        ans = match_basic_qa('谁开发的你')
        self.assertIn('Dwen', ans)
        self.assertIn('UFToolBox', ans)

    def test_skills_variants(self):
        for q in ('你会什么', '你会做什么', '你有什么技能', '你能干什么'):
            ans = match_basic_qa(q)
            self.assertIn('打开', ans, q)
            self.assertIn('插件', ans, q)

    def test_skills_en(self):
        self.assertIn('schedule tasks', match_basic_qa('what can you do'))

    def test_skills_tool_names_injected(self):
        ans = match_basic_qa('你会什么', ['plugins_operation', 'notify_operation'])
        self.assertIn('plugins_operation, notify_operation', ans)


class TestFuzzy(unittest.TestCase):
    """层 3: 模糊匹配 (插入词容错 + 防劫持)."""

    def test_inserted_word(self):
        """"你到底是谁" 子串不含 "你是谁", 靠模糊层命中."""
        self.assertIn('小U', match_basic_qa('你到底是谁'))

    def test_fuzzy_skills(self):
        ans = match_basic_qa('你究竟会什么')
        self.assertIn('打开', ans)
        self.assertIn('插件', ans)

    def test_long_question_not_hijacked(self):
        """长句真实请求 (>20 归一化字符) 不进模糊层."""
        self.assertIsNone(match_basic_qa('请详细介绍一下这个工具箱的开发背景和架构设计'))

    def test_unrelated_short_question(self):
        self.assertIsNone(match_basic_qa('今天天气怎么样'))

    def test_real_command(self):
        self.assertIsNone(match_basic_qa('打开任务调度器'))


if __name__ == '__main__':
    unittest.main()
