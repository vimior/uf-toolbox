# -*- coding: utf-8 -*-
"""Unit tests for TasksService engine."""
import threading
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from plugins.task_scheduler.task_service import (
    TasksService,
    _schedule_str,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_app():
    """Return a mock app with namespaced services."""
    svc_registry = {}

    def _register(name, fn):
        svc_registry[name] = fn

    def _call(name, *args, ns=None, **kwargs):
        if name not in svc_registry:
            raise KeyError(f"Service not registered: {name}")
        return svc_registry[name](*args, **kwargs)

    services = MagicMock()
    services.register = _register
    services.call = _call
    services.has = lambda name: name in svc_registry

    app = MagicMock()
    app.services = services
    app._app = MagicMock()

    # module(ns) returns a namespaced proxy whose .services is the same mock
    def _module(ns):
        m = MagicMock()
        m.services = services
        m.store = MagicMock()
        m.eventbus = MagicMock()
        m._infra = MagicMock()
        m._app = app
        m.emit = MagicMock()
        m.on = MagicMock()
        m.off = MagicMock()
        return m

    app.module = _module
    return app


def _mk_task(typ, fn_ref='demo@hello', **kw):
    """Build a minimal task dict."""
    base = {
        'type': typ, 'fn_ref': fn_ref,
        'auto_start': kw.pop('auto_start', True),
        'max_runs': kw.pop('max_runs', 0) or 0,
        'timeout': kw.pop('timeout', 0) or 0,
        'enabled': True,
        'last_run': 0, 'last_fired': 0, 'count': 0, 'errors': 0,
        'total_dur': 0.0, 'avg_dur': 0.0, 'max_dur': 0.0,
        'history': [],
        'created_at': time.time(),
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# _schedule_str
# ---------------------------------------------------------------------------

class TestScheduleStr(unittest.TestCase):

    def test_every(self):
        self.assertEqual(_schedule_str(_mk_task('every', interval=60)), '60s')

    def test_once_delay_seconds(self):
        self.assertEqual(_schedule_str(_mk_task('once', delay='30')), 'delay(30s)')

    def test_once_delay_at_time(self):
        self.assertEqual(_schedule_str(_mk_task('once', delay='14:30')), 'at 14:30')

    def test_once_no_delay(self):
        self.assertEqual(_schedule_str(_mk_task('once')), 'once')

    def test_once_whitespace_delay(self):
        self.assertEqual(_schedule_str(_mk_task('once', delay='  ')), 'once')

    def test_daily(self):
        self.assertEqual(_schedule_str(_mk_task('daily', time_str='03:00:00')),
                         '03:00:00')

    def test_daily_no_time(self):
        self.assertEqual(_schedule_str(_mk_task('daily')), '?')

    def test_weekly_few_days(self):
        t = _mk_task('weekly', days=[0, 2, 4], time_str='09:00')
        self.assertIn('Mo', _schedule_str(t))
        self.assertIn('We', _schedule_str(t))
        self.assertIn('Fr', _schedule_str(t))
        self.assertIn('09:00', _schedule_str(t))

    def test_weekly_many_days(self):
        t = _mk_task('weekly', days=[0, 1, 2, 3, 4], time_str='09:00')
        s = _schedule_str(t)
        self.assertIn('+3', s)  # 5 days → first 2 + "+3"

    def test_weekly_no_days(self):
        self.assertEqual(_schedule_str(_mk_task('weekly', days=[])), '?')

    def test_weekly_none_days(self):
        self.assertEqual(_schedule_str(_mk_task('weekly', days=None)), '?')

    def test_cron(self):
        self.assertEqual(
            _schedule_str(_mk_task('cron', cron_expr='*/5 * * * *')),
            '*/5 * * * *')

    def test_unknown_type(self):
        self.assertEqual(_schedule_str(_mk_task('bogus')), '?')


# ---------------------------------------------------------------------------
# TasksService — creation API
# ---------------------------------------------------------------------------

class TestTasksServiceCreation(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.svc = TasksService(app=self.app.module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_create_every(self):
        tid = self.svc._every('t1', 10, 'demo@hello')
        self.assertEqual(tid, 't1')
        t = self.svc._get('t1')
        self.assertEqual(t['type'], 'every')
        self.assertEqual(t['enabled'], True)

    def test_create_every_negative_interval(self):
        # Engine accepts any float; form validation handles the range
        tid = self.svc._every('t1', -1, 'demo@hello')
        self.assertIsNotNone(tid)

    def test_create_once_seconds(self):
        self.svc._once('once1', 5, 'demo@hello')
        t = self.svc._get('once1')
        self.assertEqual(t['type'], 'once')
        # fire_at stored internally; _get returns _task_info (no fire_at key)
        raw = self.svc._tasks['once1']
        self.assertIsNotNone(raw.get('fire_at'))

    def test_create_once_at_time(self):
        self.svc._once('once2', '23:59', 'demo@hello')
        t = self.svc._get('once2')
        self.assertEqual(t['type'], 'once')

    def test_create_once_invalid_delay(self):
        with self.assertRaises(ValueError):
            self.svc._once('bad', 'abc', 'demo@hello')

    def test_create_daily(self):
        self.svc._daily('d1', '08:00', 'demo@hello')
        t = self.svc._get('d1')
        self.assertEqual(t['type'], 'daily')
        self.assertEqual(t['time_str'], '08:00')

    def test_create_weekly(self):
        self.svc._weekly('w1', [0, 2, 4], '09:00', 'demo@hello')
        t = self.svc._get('w1')
        self.assertEqual(t['type'], 'weekly')
        self.assertEqual(t['days'], [0, 2, 4])

    def test_create_cron(self):
        self.svc._cron('c1', '*/5 * * * *', 'demo@ping')
        t = self.svc._get('c1')
        self.assertEqual(t['type'], 'cron')
        self.assertEqual(t['cron_expr'], '*/5 * * * *')

    def test_duplicate_id_raises(self):
        self.svc._every('dup', 5, 'demo@hello')
        with self.assertRaises(ValueError):
            self.svc._every('dup', 5, 'demo@hello')

    def test_update_existing(self):
        self.svc._every('upd', 5, 'demo@hello')
        self.svc._every('upd', 30, 'demo@hello', updating=True)
        t = self.svc._get('upd')
        self.assertEqual(t['interval'], 30)

    def test_updating_skips_dup_check(self):
        self.svc._every('x', 5, 'a@b')
        # should not raise
        self.svc._every('x', 10, 'a@b', updating=True)


# ---------------------------------------------------------------------------
# agent_tasks fn_args 参数通道
# ---------------------------------------------------------------------------

class TestAgentTasksFnArgs(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.svc = TasksService(app=self.app.module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_create_once_with_fn_args(self):
        r = self.svc.agent_tasks(
            'create_once', task_id='off', delay='60',
            fn_ref='notify@canvas',
            fn_args='{"text":"该下班了","pattern":"sun"}')
        self.assertEqual(r, 'off')
        raw = self.svc._tasks['off']
        self.assertEqual(raw['kwargs'],
                         {'text': '该下班了', 'pattern': 'sun'})

    def test_create_every_with_fn_args(self):
        # every/daily/weekly/cron 经 **common 透传 kwargs
        r = self.svc.agent_tasks(
            'create_every', task_id='ev', interval=10,
            fn_ref='notify@toast', fn_args='{"text":"hi"}')
        self.assertEqual(r, 'ev')
        self.assertEqual(self.svc._tasks['ev']['kwargs'], {'text': 'hi'})

    def test_fn_args_invalid_json(self):
        r = self.svc.agent_tasks(
            'create_once', task_id='bad', delay='60',
            fn_ref='notify@toast', fn_args='{oops')
        self.assertTrue(r.startswith('error:'), r)
        self.assertNotIn('bad', self.svc._tasks)

    def test_fn_args_non_object(self):
        r = self.svc.agent_tasks(
            'create_once', task_id='bad2', delay='60',
            fn_ref='notify@toast', fn_args='[1,2]')
        self.assertTrue(r.startswith('error:'), r)
        self.assertNotIn('bad2', self.svc._tasks)

    def test_no_fn_args_defaults_empty(self):
        r = self.svc.agent_tasks(
            'create_once', task_id='plain', delay='60',
            fn_ref='notify@toast')
        self.assertEqual(r, 'plain')
        self.assertEqual(self.svc._tasks['plain']['kwargs'], {})

    def test_fire_passes_kwargs_to_service(self):
        received = {}
        self.app.services.register(
            'notify@canvas',
            lambda text=None, **kw: received.update({'text': text, **kw}))
        self.svc.agent_tasks(
            'create_once', task_id='fire', delay='60',
            fn_ref='notify@canvas',
            fn_args='{"text":"该下班了","pattern":"sun"}')
        ok, _result, _ms = self.svc._call_target(
            'notify@canvas', self.svc._tasks['fire'], None)
        self.assertTrue(ok)
        self.assertEqual(received, {'text': '该下班了', 'pattern': 'sun'})


# ---------------------------------------------------------------------------
# Pause / Resume / Cancel
# ---------------------------------------------------------------------------

class TestTasksServiceLifecycle(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.svc = TasksService(app=self.app.module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_pause_resume(self):
        self.svc._every('pr', 5, 'demo@hello')
        self.assertTrue(self.svc._pause('pr'))
        t = self.svc._get('pr')
        self.assertFalse(t['enabled'])
        self.assertTrue(self.svc._resume('pr'))
        t = self.svc._get('pr')
        self.assertTrue(t['enabled'])

    def test_cancel(self):
        self.svc._every('rm', 5, 'demo@hello')
        self.assertTrue(self.svc._cancel('rm'))
        self.assertIsNone(self.svc._get('rm'))

    def test_cancel_nonexistent(self):
        self.assertFalse(self.svc._cancel('ghost'))

    def test_pause_all_resume_all(self):
        self.svc._every('a1', 5, 'd@h')
        self.svc._every('a2', 5, 'd@h')
        self.svc._pause_all()
        self.assertTrue(self.svc.global_paused)
        t1 = self.svc._get('a1')
        self.assertFalse(t1['enabled'])
        self.svc._resume_all()
        self.assertFalse(self.svc.global_paused)
        t1 = self.svc._get('a1')
        self.assertTrue(t1['enabled'])

    def test_toggle_enabled(self):
        self.svc._every('tg', 5, 'demo@hello')
        state = self.svc._toggle_enabled('tg')
        self.assertFalse(state)
        state = self.svc._toggle_enabled('tg')
        self.assertTrue(state)

    def test_toggle_nonexistent(self):
        self.assertIsNone(self.svc._toggle_enabled('ghost'))

    def test_resume_clears_failed(self):
        self.svc._every('ft', 1, 'demo@hello')
        with self.svc._lock:
            self.svc._tasks['ft']['failed'] = True
            self.svc._tasks['ft']['enabled'] = False
        self.svc._resume('ft')
        t = self.svc._get('ft')
        self.assertFalse(t['failed'])
        self.assertTrue(t['enabled'])


# ---------------------------------------------------------------------------
# _is_done
# ---------------------------------------------------------------------------

class TestIsDone(unittest.TestCase):

    def test_fired_is_done(self):
        t = _mk_task('once', fired=True)
        self.assertTrue(TasksService._is_done(t))

    def test_max_runs_reached(self):
        t = _mk_task('every', max_runs=3, count=3)
        self.assertTrue(TasksService._is_done(t))

    def test_max_runs_not_reached(self):
        t = _mk_task('every', max_runs=3, count=2)
        self.assertFalse(TasksService._is_done(t))

    def test_no_max_runs(self):
        t = _mk_task('every', count=999)
        self.assertFalse(TasksService._is_done(t))


# ---------------------------------------------------------------------------
# _skip_to_now
# ---------------------------------------------------------------------------

class TestSkipToNow(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_skip_every(self):
        t = _mk_task('every')
        self.svc._skip_to_now(t)
        self.assertGreater(t['last_run'], 0)

    def test_skip_once_already_passed(self):
        t = _mk_task('once', fire_at=0)  # always in the past
        self.svc._skip_to_now(t)
        self.assertTrue(t['fired'])

    def test_skip_once_future(self):
        t = _mk_task('once', fire_at=time.time() + 3600)
        self.svc._skip_to_now(t)
        self.assertFalse(t.get('fired', False))

    def test_skip_daily_not_yet(self):
        now = datetime.now()
        if now.hour == 23:
            # 23 点后"未来一小时"跨天, 任务时间会落在今天已过的 00:xx — 场景不成立
            self.skipTest('23:00+ has no future hour within today')
        h, m = now.hour + 1, now.minute
        t = _mk_task('daily', time_str=f'{h:02d}:{m:02d}:00')
        self.svc._skip_to_now(t)
        self.assertNotIn('last_day', t)

    def test_skip_cron(self):
        t = _mk_task('cron', cron_expr='* * * * *')
        self.svc._skip_to_now(t)
        self.assertIsNotNone(t.get('last_minute'))


# ---------------------------------------------------------------------------
# _should_fire
# ---------------------------------------------------------------------------

class TestShouldFire(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_every_ready(self):
        t = _mk_task('every', interval=10, last_run=time.time() - 20)
        self.assertTrue(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_every_not_ready(self):
        t = _mk_task('every', interval=10, last_run=time.time())
        self.assertFalse(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_once_fired_skips(self):
        t = _mk_task('once', fire_at=0, fired=True)
        self.assertFalse(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_once_ready(self):
        t = _mk_task('once', fire_at=0)  # in the past
        self.assertTrue(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_cron_matches(self):
        t = _mk_task('cron', cron_expr='* * * * *')  # every minute
        now = datetime.now()
        self.assertTrue(self.svc._should_fire(t, now, time.time()))

    def test_cron_not_matches(self):
        # a minute that doesn't match any cron pattern
        t = _mk_task('cron', cron_expr='0 0 31 2 *')  # Feb 31 — never
        self.assertFalse(self.svc._should_fire(t, datetime(2024, 7, 1, 12, 0), 0))


# ---------------------------------------------------------------------------
# _will_fire_within
# ---------------------------------------------------------------------------

class TestWillFireWithin(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_every_within(self):
        t = _mk_task('every', interval=10, last_run=time.time() - 8)
        self.assertTrue(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))

    def test_every_outside(self):
        t = _mk_task('every', interval=10, last_run=time.time() - 2)
        self.assertFalse(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))

    def test_once_within(self):
        t = _mk_task('once', fire_at=time.time() + 3)
        self.assertTrue(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))

    def test_once_fired(self):
        t = _mk_task('once', fire_at=time.time() + 3, fired=True)
        self.assertFalse(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))


# ---------------------------------------------------------------------------
# _parse_time
# ---------------------------------------------------------------------------

class TestParseTime(unittest.TestCase):

    def test_standard(self):
        self.assertEqual(TasksService._parse_time('12:30:45'), (12, 30, 45))

    def test_no_seconds(self):
        self.assertEqual(TasksService._parse_time('12:30'), (12, 30, 0))

    def test_none(self):
        self.assertEqual(TasksService._parse_time(None), (0, 0, 0))

    def test_empty(self):
        self.assertEqual(TasksService._parse_time(''), (0, 0, 0))


# ---------------------------------------------------------------------------
# _resolve_once_fire_at
# ---------------------------------------------------------------------------

class TestResolveOnceFireAt(unittest.TestCase):

    def test_seconds(self):
        at = TasksService._resolve_once_fire_at('30')
        self.assertAlmostEqual(at, time.time() + 30, delta=1)

    def test_float_seconds(self):
        at = TasksService._resolve_once_fire_at('1.5')
        self.assertAlmostEqual(at, time.time() + 1.5, delta=1)

    def test_time_string(self):
        now = datetime.now()
        t = (now.hour + 1) % 24
        at = TasksService._resolve_once_fire_at(f'{t:02d}:30')
        self.assertGreater(at, time.time())

    def test_past_time_goes_tomorrow(self):
        now = datetime.now()
        h = (now.hour - 1) % 24
        at = TasksService._resolve_once_fire_at(f'{h:02d}:{now.minute:02d}')
        self.assertGreater(at, time.time() + 3600)  # at least 1h in future

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            TasksService._resolve_once_fire_at('not_a_time')


# ---------------------------------------------------------------------------
# _base & _add_task
# ---------------------------------------------------------------------------

class TestBaseTask(unittest.TestCase):

    def test_base_defaults(self):
        t = TasksService._base('every', 'demo@hello')
        self.assertEqual(t['type'], 'every')
        self.assertEqual(t['fn_ref'], 'demo@hello')
        self.assertTrue(t['enabled'])
        self.assertEqual(t['count'], 0)
        self.assertEqual(t['errors'], 0)
        self.assertEqual(t['last_fired'], 0)
        self.assertIn('last_fired', TasksService._PRESERVE_ON_EDIT)

    def test_base_extra_fields(self):
        t = TasksService._base('daily', 'd@h', time_str='08:00')
        self.assertEqual(t['time_str'], '08:00')


class TestAddTask(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_preserve_on_edit(self):
        old = _mk_task('every', interval=10, count=5, errors=2,
                       history=[{'at': 1}])
        new = TasksService._base('every', 'demo@hello', interval=10)
        self.svc._add_task('p1', new, old_task=old)
        t = self.svc._get('p1')
        self.assertEqual(t['count'], 5)
        self.assertEqual(t['errors'], 2)
        self.assertEqual(len(t['history']), 1)

    def test_preserve_skips_missing_keys(self):
        old = _mk_task('every', interval=5)
        old.pop('history', None)
        new = TasksService._base('every', 'demo@hello', interval=5)
        self.svc._add_task('p2', new, old_task=old)
        t = self.svc._get('p2')
        self.assertIsNotNone(t)


# ---------------------------------------------------------------------------
# _task_info
# ---------------------------------------------------------------------------

class TestTaskInfo(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_info_includes_all_keys(self):
        t = _mk_task('every', interval=10)
        info = self.svc._task_info('t1', t)
        for key in ('id', 'type', 'fn_ref', 'enabled', 'count', 'errors',
                     'avg_ms', 'max_ms', 'dead', 'firing', 'fired', 'failed',
                     'last_run', 'last_fired', 'created_at', 'schedule',
                     'history'):
            self.assertIn(key, info, f'missing key: {key}')

    def test_info_last_fired_passthrough(self):
        t = _mk_task('every', interval=10, last_fired=1234.5)
        info = self.svc._task_info('t3', t)
        self.assertEqual(info['last_fired'], 1234.5)

    def test_info_values(self):
        t = _mk_task('every', interval=60)
        info = self.svc._task_info('test', t)
        self.assertEqual(info['id'], 'test')
        self.assertEqual(info['type'], 'every')
        self.assertEqual(info['enabled'], True)

    def test_dead_failed_fields(self):
        t = _mk_task('once', failed=True, dead=True)
        info = self.svc._task_info('t2', t)
        self.assertTrue(info['failed'])
        self.assertTrue(info['dead'])


# ---------------------------------------------------------------------------
# _list / _get
# ---------------------------------------------------------------------------

class TestListGet(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_list_empty(self):
        self.assertEqual(self.svc._list(), [])

    def test_list_with_tasks(self):
        self.svc._every('a', 5, 'd@h')
        self.svc._once('b', 1, 'd@h')
        result = self.svc._list()
        self.assertEqual(len(result), 2)
        ids = {t['id'] for t in result}
        self.assertEqual(ids, {'a', 'b'})

    def test_get_exists(self):
        self.svc._every('x', 5, 'd@h')
        self.assertIsNotNone(self.svc._get('x'))

    def test_get_missing(self):
        self.assertIsNone(self.svc._get('ghost'))


# ---------------------------------------------------------------------------
# args / kwargs
# ---------------------------------------------------------------------------

class TestArgsKwargs(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.svc = TasksService(app=self.app.module('tasks'))
        self._called_with = None

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def _register_spy(self, svc_name):
        def spy(*args, **kwargs):
            self._called_with = (args, kwargs)
            return 'done'
        self.app.services.register(svc_name, spy)

    def test_passes_args(self):
        self._register_spy('test@hello')
        t = self.svc._base('once', 'test@hello', args=('aa1', 'aa2'))
        self.svc._add_task('a1', t)
        self.svc.services.call('test@hello', *t['args'])
        self.assertEqual(self._called_with[0], ('aa1', 'aa2'))

    def test_passes_kwargs(self):
        self._register_spy('test@hello')
        t = self.svc._base('once', 'test@hello', kwargs={'user': 'Dwen', 'count': 3})
        self.svc._add_task('a2', t)
        self.svc.services.call('test@hello', **t['kwargs'])
        self.assertEqual(self._called_with[1], {'user': 'Dwen', 'count': 3})

    def test_passes_no_args(self):
        self._register_spy('test@hello')
        t = self.svc._base('once', 'test@hello')
        self.svc._add_task('a4', t)
        self.svc.services.call('test@hello')
        self.assertEqual(self._called_with, ((), {}))


# ---------------------------------------------------------------------------
# multi-target
# ---------------------------------------------------------------------------

class TestMultiTarget(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_create_with_comma_target(self):
        self.svc._every('multi', 60, 'demo@step1, demo@step2')
        t = self.svc._get('multi')
        self.assertIn(',', t['fn_ref'])


# ---------------------------------------------------------------------------
# _resolve_start_time
# ---------------------------------------------------------------------------

class TestResolveStartTime(unittest.TestCase):

    def test_none(self):
        self.assertIsNone(TasksService._resolve_start_time(None))

    def test_int_timestamp(self):
        ts = time.time() + 3600
        self.assertAlmostEqual(TasksService._resolve_start_time(int(ts)), ts, delta=1)

    def test_float_timestamp(self):
        ts = time.time() + 3600
        self.assertAlmostEqual(TasksService._resolve_start_time(ts), ts, delta=1)

    def test_datetime_str(self):
        at = TasksService._resolve_start_time('2026-07-30 14:30:00')
        expected = datetime(2026, 7, 30, 14, 30, 0).timestamp()
        self.assertEqual(at, expected)

    def test_time_str(self):
        now = datetime.now()
        at = TasksService._resolve_start_time(f'{now.hour:02d}:{now.minute:02d}:{now.second:02d}')
        self.assertAlmostEqual(at, now.timestamp(), delta=1)

    def test_time_str_short(self):
        at = TasksService._resolve_start_time('12:30')
        now = datetime.now()
        expected = now.replace(hour=12, minute=30, second=0, microsecond=0).timestamp()
        self.assertEqual(at, expected)

    def test_time_str_past_stays_today(self):
        """Past time string resolves to today (anchors are valid in the past)."""
        now = datetime.now()
        if now.hour < 2:
            # 凌晨 0-1 点: 今天不存在"过去 2 小时"的时刻, 场景不成立
            self.skipTest('midnight boundary: no past hour within today')
        h = now.hour - 2
        at = TasksService._resolve_start_time(f'{h:02d}:00')
        expected = now.replace(hour=h, minute=0, second=0, microsecond=0).timestamp()
        self.assertAlmostEqual(at, expected, delta=1)
        # Should NOT be tomorrow
        self.assertLess(at, now.timestamp() + 1)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            TasksService._resolve_start_time('not_a_time')


# ---------------------------------------------------------------------------
# _resolve_once_fire_at — enhanced formats
# ---------------------------------------------------------------------------

class TestResolveOnceFireAtEnhanced(unittest.TestCase):

    def test_absolute_datetime(self):
        at = TasksService._resolve_once_fire_at('2026-07-30 14:30:00')
        expected = datetime(2026, 7, 30, 14, 30, 0).timestamp()
        self.assertEqual(at, expected)

    def test_large_number_still_relative(self):
        """Numbers (even large) are always relative seconds. Use datetime string for absolute times."""
        at = TasksService._resolve_once_fire_at(1_800_000_000)
        self.assertAlmostEqual(at, time.time() + 1_800_000_000, delta=1)

    def test_relative_seconds_small_number(self):
        """Small numbers are treated as relative seconds."""
        at = TasksService._resolve_once_fire_at(30)
        self.assertAlmostEqual(at, time.time() + 30, delta=1)

    def test_time_string_still_works(self):
        """Original time string behavior preserved."""
        now = datetime.now()
        h = (now.hour + 1) % 24
        at = TasksService._resolve_once_fire_at(f'{h:02d}:30')
        self.assertGreater(at, time.time())

    def test_relative_seconds_string(self):
        at = TasksService._resolve_once_fire_at('60')
        self.assertAlmostEqual(at, time.time() + 60, delta=1)


# ---------------------------------------------------------------------------
# _should_fire — every with start_time
# ---------------------------------------------------------------------------

class TestShouldFireEveryStartTime(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_without_start_time_backward_compat(self):
        """No start_time: existing behavior unchanged."""
        t = _mk_task('every', interval=10, last_run=time.time() - 20)
        self.assertTrue(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_without_start_time_not_ready(self):
        t = _mk_task('every', interval=10, last_run=time.time())
        self.assertFalse(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_start_in_future_waits(self):
        """Scenario 3: start_time is in the future."""
        future = time.time() + 3600
        t = _mk_task('every', interval=10, last_run=0, start_time=future)
        self.assertFalse(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_first_slot_not_reached(self):
        """Scenario 1: start+interval hasn't arrived yet."""
        now = time.time()
        t = _mk_task('every', interval=10, last_run=now, start_time=now)
        # first_slot = now + 10, so now < first_slot
        self.assertFalse(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_first_slot_reached(self):
        """First slot arrived."""
        now = time.time()
        t = _mk_task('every', interval=10, last_run=now - 20, start_time=now - 20)
        # start_time = now-20, first_slot = now-10, now >= first_slot
        self.assertTrue(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_skip_missed_slot(self):
        """Scenario 2: created late, skip missed slot, wait for next."""
        now = time.time()
        # start=now-15, interval=10. Slot 1: now-5 (missed). Slot 2: now+5 (next).
        t = _mk_task('every', interval=10, last_run=now, start_time=now - 15)
        # last_run=now, base=max(now, now-15)=now, k=int(now-(now-15))/10+1=1+1=2
        # next_slot = now-15 + 20 = now+5, now >= now+5? False
        self.assertFalse(self.svc._should_fire(t, datetime.now(), time.time()))

        # After 6 seconds: next_slot should be reached
        later = time.time() + 6
        t2 = _mk_task('every', interval=10, last_run=now, start_time=now - 15)
        self.assertTrue(self.svc._should_fire(t2, datetime.now(), later))

    def test_normal_sequence(self):
        """After firing, next slot is correctly calculated."""
        now = time.time()
        # Fired at now-10, next slot at now
        t = _mk_task('every', interval=10, last_run=now - 10, start_time=now - 20)
        # base=max(now-10, now-20)=now-10, k=int((now-10-(now-20))/10)+1=1+1=2
        # next_slot = now-20+20 = now
        self.assertTrue(self.svc._should_fire(t, datetime.now(), time.time()))

    def test_long_execution_no_double_fire(self):
        """After long execution that skips a slot, don't double-fire."""
        now = time.time()
        # Fired at now-25, execution took 15s, so last_run=now-10
        # start=now-40, interval=10. Slot at now-20, now-10, now.
        t = _mk_task('every', interval=10, last_run=now - 10, start_time=now - 40)
        # base=now-10, k=int((now-10-(now-40))/10)+1=3+1=4, next_slot=now-40+40=now
        self.assertTrue(self.svc._should_fire(t, datetime.now(), time.time()))


# ---------------------------------------------------------------------------
# _will_fire_within — every with start_time
# ---------------------------------------------------------------------------

class TestWillFireWithinEveryStartTime(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_without_start_time(self):
        t = _mk_task('every', interval=10, last_run=time.time() - 8)
        self.assertTrue(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))

    def test_with_start_time_within(self):
        now = time.time()
        t = _mk_task('every', interval=10, last_run=now - 8, start_time=now - 18)
        # next_slot = now-18 + k*10, base=now-8, k=int((now-8-(now-18))/10)+1=2
        # next_slot = now-18+20 = now+2, within 5 secs
        self.assertTrue(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))

    def test_with_start_time_outside(self):
        now = time.time()
        t = _mk_task('every', interval=10, last_run=now, start_time=now)
        # first_slot = now+10, 10 > 5
        self.assertFalse(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))

    def test_start_in_future(self):
        future = time.time() + 3600
        t = _mk_task('every', interval=10, last_run=0, start_time=future)
        self.assertFalse(self.svc._will_fire_within(
            t, datetime.now(), time.time(), 5))


# ---------------------------------------------------------------------------
# _skip_to_now — every with start_time
# ---------------------------------------------------------------------------

class TestSkipToNowEveryStartTime(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_skip_every_with_start_time_preserves_anchor(self):
        """Scenario 4: resume keeps start_time, only updates last_run."""
        anchor = time.time() - 100
        t = _mk_task('every', interval=10, last_run=time.time() - 50, start_time=anchor)
        self.svc._skip_to_now(t)
        self.assertGreater(t['last_run'], anchor)
        self.assertEqual(t['start_time'], anchor)  # anchor unchanged

    def test_skip_every_without_start_time(self):
        """No start_time: existing behavior."""
        t = _mk_task('every', interval=10, last_run=0)
        self.svc._skip_to_now(t)
        self.assertGreater(t['last_run'], 0)


# ---------------------------------------------------------------------------
# every creation — start_time integration
# ---------------------------------------------------------------------------

class TestEveryStartTimeCreation(unittest.TestCase):

    def setUp(self):
        self.app = _make_app()
        self.svc = TasksService(app=self.app.module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_create_every_with_start_time(self):
        ts = time.time() + 60
        tid = self.svc._every('est1', 10, 'demo@hello', start_time=ts)
        t = self.svc._get('est1')
        self.assertEqual(t['start_time'], ts)

    def test_create_every_without_start_time(self):
        tid = self.svc._every('est2', 10, 'demo@hello')
        t = self.svc._get('est2')
        self.assertIsNone(t.get('start_time'))

    def test_create_every_with_time_str(self):
        tid = self.svc._every('est3', 10, 'demo@hello', start_time='08:00:00')
        t = self.svc._get('est3')
        self.assertIsNotNone(t['start_time'])
        # should resolve to today 08:00
        expected = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0).timestamp()
        self.assertAlmostEqual(t['start_time'], expected, delta=1)

    def test_edit_preserves_start_time(self):
        """Editing should preserve start_time via _add_task's PRESERVE_ON_EDIT."""
        ts = time.time() + 60
        self.svc._every('est4', 10, 'demo@hello', start_time=ts)
        # Edit: update interval
        self.svc._every('est4', 20, 'demo@hello', start_time=ts, updating=True)
        t = self.svc._get('est4')
        self.assertEqual(t['interval'], 20)
        self.assertEqual(t['start_time'], ts)


# ---------------------------------------------------------------------------
# _restart — 完成的任务重新执行
# ---------------------------------------------------------------------------

class TestRestart(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_restart_registered(self):
        self.assertTrue(hasattr(self.svc, '_restart'))

    def test_restart_once_rebuilds_fire_at(self):
        """once 完成 (fired) 但 enabled=True → restart 重建计时."""
        delay = 30
        self.svc._once('t1', delay, 'demo@hello')
        with self.svc._lock:
            t = self.svc._tasks['t1']
            t['fired'] = True
            t['count'] = 1
        self.assertTrue(self.svc._restart('t1'))
        t = self.svc._tasks['t1']
        self.assertFalse(t['fired'])
        self.assertTrue(t['enabled'])
        self.assertEqual(t['count'], 0)
        self.assertAlmostEqual(t['fire_at'], time.time() + delay, delta=1)

    def test_restart_max_runs_resets_counter_keeps_history(self):
        """max_runs 已满 → 清零执行计数, 历史保留."""
        self.svc._every('t2', 60, 'demo@hello', max_runs=3)
        with self.svc._lock:
            t = self.svc._tasks['t2']
            t['count'] = 3
            t['errors'] = 2
            t['total_dur'] = 3.5
            t['avg_dur'] = 1.2
            t['max_dur'] = 2.0
            t['history'] = [{'at': 1, 'ok': True}]
            t['enabled'] = False
        self.assertTrue(self.svc._restart('t2'))
        t = self.svc._tasks['t2']
        self.assertTrue(t['enabled'])
        self.assertEqual(t['count'], 0)
        self.assertEqual(t['errors'], 0)
        self.assertEqual(t['total_dur'], 0.0)
        self.assertEqual(t['avg_dur'], 0.0)
        self.assertEqual(t['max_dur'], 0.0)
        self.assertEqual(len(t['history']), 1)  # 历史保留

    def test_restart_every_aligns_timer(self):
        """every restart 走 _skip_to_now 对齐到最近过去槽位 (保持相位, 不立即触发)."""
        self.svc._every('t3', 60, 'demo@hello')
        with self.svc._lock:
            self.svc._tasks['t3']['last_run'] = time.time() - 999
        self.svc._restart('t3')
        t = self.svc._tasks['t3']
        remaining = (t['last_run'] + 60) - time.time()
        self.assertGreater(t['last_run'], time.time() - 60)  # 对齐到槽位
        self.assertGreater(remaining, 0)  # 不立即触发

    def test_restart_nonexistent(self):
        self.assertFalse(self.svc._restart('ghost'))

    def test_restart_clears_failed(self):
        self.svc._daily('t4', '08:00', 'demo@hello')
        with self.svc._lock:
            self.svc._tasks['t4']['failed'] = True
            self.svc._tasks['t4']['dead'] = True
        self.svc._restart('t4')
        t = self.svc._tasks['t4']
        self.assertFalse(t['failed'])
        self.assertFalse(t['dead'])
        self.assertTrue(t['enabled'])


# ---------------------------------------------------------------------------
# _skip_to_now — every 重启相位保持 (对齐到最近过去槽位)
# ---------------------------------------------------------------------------

class TestSkipToNowEveryPhase(unittest.TestCase):

    def setUp(self):
        self.svc = TasksService(app=_make_app().module('tasks'))

    def tearDown(self):
        if hasattr(self.svc, 'on_stop'):
            self.svc.on_stop()

    def test_skip_aligns_to_past_slot(self):
        """停机 3.5 周期 → 跳过 3 个过期周期, 剩 0.5 周期, 不立即触发."""
        interval = 10.0
        t = _mk_task('every', interval=interval, last_run=time.time() - 35)
        self.svc._skip_to_now(t)
        remaining = (t['last_run'] + interval) - time.time()
        self.assertAlmostEqual(remaining, 5, delta=1)

    def test_skip_alignment_is_idempotent(self):
        """连续对齐两次结果一致 (resume 后再对齐不漂移)."""
        interval = 10.0
        t = _mk_task('every', interval=interval, last_run=time.time() - 25)
        self.svc._skip_to_now(t)
        first = t['last_run']
        self.svc._skip_to_now(t)
        self.assertAlmostEqual(t['last_run'], first, delta=0.5)

    def test_skip_never_run_uses_now(self):
        """从未执行 (last_run=0) → 兜底 now, 不立即触发."""
        t = _mk_task('every', interval=10, last_run=0)
        self.svc._skip_to_now(t)
        self.assertAlmostEqual(t['last_run'], time.time(), delta=1)
