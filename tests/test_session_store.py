# -*- coding: utf-8 -*-
"""Unit tests for SessionStore (sqlite 多会话存储) + 服务层会话管理."""
import os
import tempfile
import threading
import unittest
from unittest.mock import MagicMock

from plugins.ai_assistant.core.session_store import SessionStore

MSGS = [
    {'role': 'user', 'content': '打开任务调度器'},
    {'role': 'assistant', 'content': '', 'tool_calls': [
        {'id': 'call_1', 'type': 'function',
         'function': {'name': 'plugins_operation',
                      'arguments': '{"action": "start"}'}}]},
    {'role': 'tool', 'tool_call_id': 'call_1', 'content': '{"task_panel": "ok"}'},
    {'role': 'assistant', 'content': '已帮你打开插件: 任务调度'},
]


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = SessionStore(os.path.join(self.tmp, 'test.db'))

    def tearDown(self):
        self.store.close()

    def test_create_and_list(self):
        sid = self.store.create()
        self.assertTrue(sid)
        sessions = self.store.list()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]['id'], sid)
        self.assertEqual(sessions[0]['msg_count'], 0)
        self.assertTrue(self.store.exists(sid))

    def test_append_messages_roundtrip(self):
        sid = self.store.create()
        self.store.append(sid, MSGS)
        self.assertEqual(self.store.messages(sid), MSGS)
        sessions = self.store.list()
        self.assertEqual(sessions[0]['msg_count'], len(MSGS))

    def test_append_empty_noop(self):
        sid = self.store.create()
        self.store.append(sid, [])
        self.assertEqual(self.store.messages(sid), [])

    def test_persistence_across_reopen(self):
        sid = self.store.create(title='旧会话')
        self.store.append(sid, [{'role': 'user', 'content': 'hi'}])
        self.store.close()
        store2 = SessionStore(os.path.join(self.tmp, 'test.db'))
        try:
            sessions = store2.list()
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]['title'], '旧会话')
            self.assertEqual(store2.messages(sid),
                             [{'role': 'user', 'content': 'hi'}])
        finally:
            store2.close()

    def test_clear_keeps_session(self):
        sid = self.store.create()
        self.store.append(sid, [{'role': 'user', 'content': 'x'}])
        self.store.clear(sid)
        self.assertEqual(self.store.messages(sid), [])
        self.assertTrue(self.store.exists(sid))

    def test_delete_removes_session_and_messages(self):
        sid = self.store.create()
        self.store.append(sid, [{'role': 'user', 'content': 'x'}])
        self.store.delete(sid)
        self.assertFalse(self.store.exists(sid))
        self.assertEqual(self.store.messages(sid), [])

    def test_set_title_if_untitled_only_once(self):
        sid = self.store.create()
        self.store.set_title_if_untitled(sid, '第一条问题')
        self.store.set_title_if_untitled(sid, '第二条问题')
        self.assertEqual(self.store.list()[0]['title'], '第一条问题')
        # 空白标题不覆盖
        self.store.set_title_if_untitled(sid, '   ')
        self.assertEqual(self.store.list()[0]['title'], '第一条问题')

    def test_rename(self):
        sid = self.store.create(title='a')
        self.store.rename(sid, 'b')
        self.assertEqual(self.store.list()[0]['title'], 'b')

    def test_list_ordered_by_last_message_time(self):
        """最近活跃优先: 有消息的按最后一条消息时间排, 空会话按创建时间."""
        s1 = self.store.create(title='one')
        s2 = self.store.create(title='two')
        ids = [s['id'] for s in self.store.list()]
        self.assertEqual(ids, [s2, s1])            # 空会话: 新创建在前
        self.store.append(s1, [{'role': 'user', 'content': 'hi'}])
        ids = [s['id'] for s in self.store.list()]
        self.assertEqual(ids[0], s1)               # 聊过天的浮到最上

    def test_rename_and_title_do_not_reorder(self):
        """重命名/自动生成标题不改动排序 (排序只认消息活跃时间)."""
        s1 = self.store.create(title='one')
        s2 = self.store.create(title='two')
        self.store.append(s1, [{'role': 'user', 'content': 'hi'}])
        self.store.rename(s2, '改名')
        self.store.set_title_if_untitled(s2, '自动标题')
        ids = [s['id'] for s in self.store.list()]
        self.assertEqual(ids[0], s1)

    def test_add_usage_accumulates(self):
        sid = self.store.create()
        self.store.add_usage(sid, {'total_tokens': 100, 'prompt_tokens': 60,
                                   'completion_tokens': 40, 'cache_hit': 10})
        self.store.add_usage(sid, {'total_tokens': 50, 'prompt_tokens': 30,
                                   'completion_tokens': 20, 'cache_hit': 5,
                                   'unknown_key': 999})
        u = self.store.list()[0]['usage']
        self.assertEqual(u['total_tokens'], 150)
        self.assertEqual(u['prompt_tokens'], 90)
        self.assertEqual(u['completion_tokens'], 60)
        self.assertEqual(u['cache_hit'], 15)
        self.assertNotIn('unknown_key', u)

    def test_add_usage_ignores_invalid(self):
        sid = self.store.create()
        self.store.add_usage(sid, None)
        self.store.add_usage(sid, 'not-a-dict')
        self.store.add_usage(sid, {'total_tokens': 0})
        self.store.add_usage(9999, {'total_tokens': 1})   # 不存在的会话
        self.assertIsNone(self.store.list()[0]['usage'])

    def test_clear_resets_usage(self):
        sid = self.store.create()
        self.store.add_usage(sid, {'total_tokens': 100})
        self.store.clear(sid)
        self.assertIsNone(self.store.list()[0]['usage'])
        self.assertTrue(self.store.exists(sid))

    def test_migrate_old_db_without_usage_column(self):
        """v1 旧库 (无 usage 列) 打开时自动补列."""
        import sqlite3
        old = os.path.join(self.tmp, 'old.db')
        conn = sqlite3.connect(old)
        conn.execute('CREATE TABLE sessions (id INTEGER PRIMARY KEY,'
                     " title TEXT NOT NULL DEFAULT '', created_at REAL,"
                     ' updated_at REAL)')
        conn.execute('INSERT INTO sessions(title, created_at, updated_at)'
                     " VALUES ('旧会话', 1.0, 1.0)")
        conn.commit()
        conn.close()
        store2 = SessionStore(old)
        try:
            sessions = store2.list()
            self.assertEqual(sessions[0]['title'], '旧会话')
            sid = sessions[0]['id']
            store2.add_usage(sid, {'total_tokens': 7})
            self.assertEqual(store2.list()[0]['usage']['total_tokens'], 7)
        finally:
            store2.close()

    def test_sessions_isolated(self):
        s1 = self.store.create()
        s2 = self.store.create()
        self.store.append(s1, [{'role': 'user', 'content': 'A'}])
        self.store.append(s2, [{'role': 'user', 'content': 'B'}])
        self.assertEqual(self.store.messages(s1)[0]['content'], 'A')
        self.assertEqual(self.store.messages(s2)[0]['content'], 'B')


# ---------------------------------------------------------------------------
# 服务层会话管理 (AgentService 多会话服务, 不经 __init__)
# ---------------------------------------------------------------------------

from plugins.ai_assistant.agent_service import AgentService  # noqa: E402


def make_service():
    svc = AgentService.__new__(AgentService)
    svc._lock = threading.Lock()
    svc._store = SessionStore(':memory:')
    svc._session_id = svc._store.create()
    svc._session = []
    svc._saved_len = 0
    svc._stops = {}
    svc._confirms = {}
    svc._queue = MagicMock()
    return svc


class TestServiceSessions(unittest.TestCase):
    def setUp(self):
        self.svc = make_service()

    def test_create_session_switches(self):
        old = self.svc._session_id
        self.svc._commit(old, [{'role': 'user', 'content': 'old'}])
        new = self.svc._svc_create_session()
        self.assertNotEqual(new, old)
        self.assertEqual(self.svc._session_id, new)
        self.assertEqual(self.svc._session, [])
        self.assertEqual(len(self.svc._store.list()), 2)

    def test_switch_session_loads_messages(self):
        sid_a = self.svc._session_id
        self.svc._commit(sid_a, [{'role': 'user', 'content': 'A'}])
        sid_b = self.svc._svc_create_session()
        self.assertTrue(self.svc._svc_switch_session(sid_a))
        self.assertEqual(self.svc._session_id, sid_a)
        self.assertEqual(len(self.svc._session), 1)
        self.assertTrue(self.svc._svc_switch_session(sid_b))
        self.assertEqual(self.svc._session, [])

    def test_switch_unknown_session_fails(self):
        self.assertFalse(self.svc._svc_switch_session(9999))
        self.assertEqual(self.svc._session, [])

    def test_commit_to_other_session_not_in_memory(self):
        """用户中途切换会话: 旧会话写回只进库, 不污染当前内存缓存."""
        sid_a = self.svc._session_id
        sid_b = self.svc._svc_create_session()
        self.svc._commit(sid_a, [{'role': 'assistant', 'content': '迟到写回'}])
        self.assertEqual(self.svc._session, [])            # 当前会话不受影响
        self.assertEqual(self.svc._store.messages(sid_a)[0]['content'],
                         '迟到写回')

    def test_commit_current_session_persists_incrementally(self):
        sid = self.svc._session_id
        self.svc._commit(sid, [{'role': 'user', 'content': 'u'}])
        self.assertEqual(self.svc._saved_len, 1)
        self.svc._commit(sid, [{'role': 'assistant', 'content': 'a'}])
        self.assertEqual(self.svc._saved_len, 2)
        self.assertEqual(len(self.svc._store.messages(sid)), 2)

    def test_delete_current_switches_to_latest(self):
        sid_a = self.svc._session_id
        sid_b = self.svc._svc_create_session()
        cur = self.svc._svc_delete_session(sid_b)
        self.assertEqual(cur, sid_a)
        self.assertEqual(self.svc._session_id, sid_a)

    def test_delete_last_session_creates_new(self):
        sid = self.svc._session_id
        cur = self.svc._svc_delete_session(sid)
        self.assertNotEqual(cur, sid)
        self.assertEqual(self.svc._session_id, cur)
        self.assertEqual(self.svc._session, [])

    def test_clear_session_uses_store(self):
        sid = self.svc._session_id
        self.svc._commit(sid, [{'role': 'user', 'content': 'x'}])
        self.assertTrue(self.svc._svc_clear_session())
        self.assertEqual(self.svc._session, [])
        self.assertEqual(self.svc._saved_len, 0)
        self.assertEqual(self.svc._store.messages(sid), [])
        self.assertTrue(self.svc._store.exists(sid))

    def test_rename_session(self):
        sid = self.svc._session_id
        self.assertTrue(self.svc._svc_rename_session(sid, ' renamed '))
        self.assertEqual(self.svc._store.list()[0]['title'], ' renamed ')
        self.assertFalse(self.svc._svc_rename_session(9999, 'x'))

    def test_auto_title_from_first_question(self):
        sid = self.svc._session_id
        self.svc._auto_title(sid, '  打开\n任务调度器  ')
        self.assertEqual(self.svc._store.list()[0]['title'], '打开 任务调度器')

    def test_auto_title_truncated_to_10(self):
        """标题截断 10 字 — 侧栏 180px 宽度约束."""
        sid = self.svc._session_id
        self.svc._auto_title(sid, '一二三四五六七八九十十一十二十三')
        self.assertEqual(self.svc._store.list()[0]['title'],
                         '一二三四五六七八九十')


if __name__ == '__main__':
    unittest.main()
