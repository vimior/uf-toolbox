# -*- coding: utf-8 -*-
"""会话存储 — sqlite 持久化 (多会话).

- WAL 模式 + 单连接 + RLock: agent 工作线程 / 主线程并发安全
- 消息全量保留, 上下文窗口由调用方取尾部 (服务层 _MAX_SESSION_MSGS)
- 排序按最后一条消息时间 (最近活跃优先); rename/标题生成不改动排序
- 消息 dict 形态对齐原 JSON 会话:
  {'role','content', 'tool_calls'?, 'tool_call_id'?}
- meta 列预留 (JSON, 存 usage/timing 等轮次级元数据), v1 不写入
- sessions.usage 列 (JSON) 存会话级 token 累计, 供状态栏按会话展示
"""
import json
import os
import sqlite3
import threading
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    usage TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    tool_call_id TEXT,
    meta TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
"""


class SessionStore:
    """多会话存储. 所有方法线程安全, 均可在工作线程直接调用."""

    def __init__(self, path):
        self._path = path
        self._lock = threading.RLock()
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA busy_timeout=3000')
        self._conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self):
        """旧库补列 — v2: sessions.usage (会话级 token 累计)."""
        with self._lock, self._conn:
            cols = [r['name'] for r in self._conn.execute(
                'PRAGMA table_info(sessions)')]
            if 'usage' not in cols:
                self._conn.execute(
                    'ALTER TABLE sessions ADD COLUMN usage TEXT')

    # ---- sessions ----

    def create(self, title=''):
        now = time.time()
        with self._lock, self._conn:
            cur = self._conn.execute(
                'INSERT INTO sessions(title, created_at, updated_at)'
                ' VALUES (?,?,?)', (title, now, now))
            return cur.lastrowid

    def list(self):
        """按最后一条消息时间倒序 (最近活跃优先).

        有消息的会话按 MAX(messages.created_at) 排, 空会话回退创建时间 —
        rename/自动生成标题不改动排序 (updated_at 仅由消息 append/clear 驱动).
        """
        with self._lock:
            rows = self._conn.execute(
                'SELECT s.id, s.title, s.usage, s.created_at, s.updated_at,'
                ' (SELECT COUNT(*) FROM messages m'
                '   WHERE m.session_id = s.id) AS msg_count,'
                ' COALESCE((SELECT MAX(m.created_at) FROM messages m'
                '   WHERE m.session_id = s.id), s.created_at) AS last_active'
                ' FROM sessions s ORDER BY last_active DESC').fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['usage'] = json.loads(d['usage']) if d['usage'] else None
            out.append(d)
        return out

    def exists(self, sid):
        with self._lock:
            row = self._conn.execute(
                'SELECT 1 FROM sessions WHERE id=?', (sid,)).fetchone()
        return row is not None

    def rename(self, sid, title):
        """重命名不改 updated_at — 排序只认消息活跃时间."""
        with self._lock, self._conn:
            self._conn.execute(
                'UPDATE sessions SET title=? WHERE id=?',
                (str(title), sid))

    def set_title_if_untitled(self, sid, title):
        """首条用户消息自动生成标题 (已有标题不动). 不改动排序."""
        title = str(title).strip()
        if not title:
            return
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE sessions SET title=?"
                " WHERE id=? AND title=''", (title, sid))

    def add_usage(self, sid, usage):
        """会话级 token 累计 (与面板状态栏口径一致).

        usage: {'total_tokens','prompt_tokens','completion_tokens',
        'cache_hit'?} — 缺省键按 0 计; 未知键忽略.
        """
        if not isinstance(usage, dict):
            return
        keys = ('total_tokens', 'prompt_tokens', 'completion_tokens',
                'cache_hit')
        delta = {k: int(usage.get(k) or 0) for k in keys}
        if not any(delta.values()):
            return
        with self._lock, self._conn:
            row = self._conn.execute(
                'SELECT usage FROM sessions WHERE id=?', (sid,)).fetchone()
            if row is None:
                return
            cur = json.loads(row['usage']) if row['usage'] else {}
            for k in keys:
                cur[k] = int(cur.get(k) or 0) + delta[k]
            self._conn.execute(
                'UPDATE sessions SET usage=? WHERE id=?',
                (json.dumps(cur, ensure_ascii=False), sid))

    # ---- messages ----

    def messages(self, sid):
        """按序返回会话全部消息 (dict 形态, 与旧 JSON 会话一致)."""
        with self._lock:
            rows = self._conn.execute(
                'SELECT role, content, tool_calls, tool_call_id, meta'
                ' FROM messages WHERE session_id=? ORDER BY id',
                (sid,)).fetchall()
        out = []
        for r in rows:
            m = {'role': r['role'], 'content': r['content']}
            if r['tool_calls']:
                m['tool_calls'] = json.loads(r['tool_calls'])
            if r['tool_call_id']:
                m['tool_call_id'] = r['tool_call_id']
            out.append(m)
        return out

    def append(self, sid, msgs):
        """批量追加消息并刷新会话时间. msgs 为 session 形态 dict."""
        if not msgs:
            return
        now = time.time()
        rows = [(
            sid,
            m.get('role', ''),
            m.get('content') or '',
            json.dumps(m['tool_calls'], ensure_ascii=False)
            if m.get('tool_calls') else None,
            m.get('tool_call_id'),
            json.dumps(m['meta'], ensure_ascii=False)
            if m.get('meta') else None,
            now,
        ) for m in msgs]
        with self._lock, self._conn:
            self._conn.executemany(
                'INSERT INTO messages'
                '(session_id, role, content, tool_calls, tool_call_id,'
                ' meta, created_at) VALUES (?,?,?,?,?,?,?)', rows)
            self._conn.execute(
                'UPDATE sessions SET updated_at=? WHERE id=?', (now, sid))

    def clear(self, sid):
        """清空会话消息与 usage 累计 (保留会话本身, 对齐原 clear_session 语义)."""
        with self._lock, self._conn:
            self._conn.execute('DELETE FROM messages WHERE session_id=?',
                               (sid,))
            self._conn.execute(
                "UPDATE sessions SET usage=NULL, updated_at=?"
                " WHERE id=?", (time.time(), sid))

    def delete(self, sid):
        """删除会话及其全部消息."""
        with self._lock, self._conn:
            self._conn.execute('DELETE FROM messages WHERE session_id=?',
                               (sid,))
            self._conn.execute('DELETE FROM sessions WHERE id=?', (sid,))

    def close(self):
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
