# -*- coding: utf-8 -*-
"""Task scheduler engine — ServicePlugin, runs headless.

Provides services for other plugins:
  tasks@create_every(id, interval_s, fn_ref, max_runs=0, timeout=0)
  tasks@create_once (id, delay, fn_ref, timeout=0)
  tasks@create_daily(id, time_str, fn_ref, max_runs=0, timeout=0)
  tasks@create_weekly(id, [days], time_str, fn_ref, max_runs=0, timeout=0)
  tasks@create_cron (id, cron_expr, fn_ref, max_runs=0, timeout=0)
  tasks@cancel(id)   tasks@pause(id)   tasks@resume(id)
  tasks@list()        tasks@get(id)

Target fn_ref supports comma-separated multiple services:
  "ns@method1, ns@method2"
"""
import concurrent.futures
import threading
import time
from datetime import datetime, timedelta

from plugins.plugin import ServicePlugin
from plugins.task_scheduler._cron_utils import (
    _WEEKDAY_NAMES,
    cron_matches,
)

_MAX_HISTORY = 10


# ---------------------------------------------------------------------------
# schedule display
# ---------------------------------------------------------------------------


def _schedule_str(task):
    """Human-readable schedule string (used by _task_info and panel)."""
    tp = task['type']
    if tp == 'every':
        return f"{task['interval']}s"
    if tp == 'once':
        dly = task.get('delay', '')
        if not dly:
            return 'once'
        s = str(dly).strip()
        if not s:
            return 'once'
        try:
            float(s)
            return f'delay({s}s)'
        except ValueError:
            pass
        if ':' in s:
            return f'at {s}'
        return f'delay({s}s)'
    if tp == 'daily':
        t = task.get('time_str', '?')
        return t[:8] if ':' in (t or '') else t
    if tp == 'weekly':
        days = sorted(task.get('days') or [])
        if not days:
            return '?'
        if len(days) <= 3:
            ds = ''.join(_WEEKDAY_NAMES[d][:2] for d in days)
        else:
            ds = ''.join(_WEEKDAY_NAMES[d][:2] for d in days[:2]) + f'+{len(days)-2}'
        t = task.get('time_str', '?')
        return f"{ds} {t[:5]}" if ':' in (t or '') else ds
    if tp == 'cron':
        return task.get('cron_expr', '?')
    return '?'


# ---------------------------------------------------------------------------
# engine
# ---------------------------------------------------------------------------

class TasksService(ServicePlugin):
    name = 'Tasks Engine'
    name_zh = '任务引擎'
    namespace = 'tasks'

    # Fields preserved across edits
    _PRESERVE_ON_EDIT = ('count', 'errors', 'total_dur', 'avg_dur',
                         'max_dur', 'history', 'last_run', 'created_at',
                         'failed')

    def __init__(self, app=None):
        super().__init__(app)
        self._tasks = {}
        self._lock = threading.Lock()
        self._global_paused = False
        self._pre_pause_state = {}
        self._prewarmed = {}

        # ---- register public API ----
        s = self.services
        s.register('create_every', self._every)
        s.register('create_once', self._once)
        s.register('create_daily', self._daily)
        s.register('create_weekly', self._weekly)
        s.register('create_cron', self._cron)
        s.register('cancel', self._cancel)
        s.register('pause', self._pause)
        s.register('resume', self._resume)
        s.register('list', self._list)
        s.register('get', self._get)

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self._start_tick()

    # ===================================================================
    #  timer
    # ===================================================================

    def _start_tick(self):
        self._tick()

    def _tick(self):
        try:
            self._tick_impl()
        except Exception:
            import traceback
            traceback.print_exc()
        if self.root:
            self.root.after(1000, self._tick)

    def _tick_impl(self):
        now = datetime.now()
        now_ts = time.time()

        with self._lock:
            tasks_snapshot = list(self._tasks.items())

        for task_id, task in tasks_snapshot:
            if task.get('dead') or not task.get('enabled', True) or task.get('firing'):
                continue
            if task.get('max_runs') and task['count'] >= task['max_runs']:
                continue
            if (task.get('auto_start', True) and
                    self._will_fire_within(task, now, now_ts, 5)):
                self._prewarm_targets(task['fn_ref'])
            if self._should_fire(task, now, now_ts):
                fire = False
                with self._lock:
                    t = self._tasks.get(task_id)
                    if (t and not t.get('dead') and t.get('enabled', True)
                            and not t.get('firing')):
                        if not (t.get('max_runs') and t['count'] >= t['max_runs']):
                            t['firing'] = True
                            t['last_run'] = now_ts
                            fire = True
                if fire:
                    self._executor.submit(self._fire, task_id)

    def _should_fire(self, task, now, now_ts):
        tp = task['type']
        if tp == 'every':
            return now_ts - task['last_run'] >= task['interval']
        if tp == 'once':
            return not task.get('fired') and now_ts >= task['fire_at']
        if tp == 'daily':
            target = task['time_str']
            h, m, s = self._parse_time(target)
            target_secs = h * 3600 + m * 60 + s
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            if now_secs >= target_secs:
                dk = now.strftime('%Y-%m-%d')
                if task.get('last_day') != dk:
                    task['last_day'] = dk
                    return True
            return False
        if tp == 'weekly':
            target = task['time_str']
            h, m, s = self._parse_time(target)
            target_secs = h * 3600 + m * 60 + s
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            if now_secs >= target_secs:
                dk = now.strftime('%Y-%m-%d')
                dow = now.weekday()
                if dow in (task.get('days') or []) and task.get('last_day') != dk:
                    task['last_day'] = dk
                    return True
            return False
        if tp == 'cron':
            dk = now.strftime('%Y-%m-%d %H:%M')
            if cron_matches(task.get('cron_expr', ''), now) and task.get('last_minute') != dk:
                task['last_minute'] = dk
                return True
            return False
        return False

    def _will_fire_within(self, task, now, now_ts, seconds):
        tp = task['type']
        if tp == 'every':
            return (task['last_run'] + task['interval']) - now_ts <= seconds
        if tp == 'once':
            return (not task.get('fired') and
                    task.get('fire_at', 0) - now_ts <= seconds)
        if tp in ('daily', 'weekly'):
            target = task['time_str']
            h, m, s = self._parse_time(target)
            target_secs = h * 3600 + m * 60 + s
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            diff = target_secs - now_secs
            if diff < 0:
                return False
            if diff > seconds:
                return False
            if tp == 'weekly':
                dow = now.weekday()
                if dow not in (task.get('days') or []):
                    return False
            dk = now.strftime('%Y-%m-%d')
            return task.get('last_day') != dk
        if tp == 'cron':
            check_dt = now.replace(second=0, microsecond=0)
            for _ in range(2):
                if cron_matches(task.get('cron_expr', ''), check_dt):
                    dk = check_dt.strftime('%Y-%m-%d %H:%M')
                    if task.get('last_minute') != dk:
                        return True
                check_dt += timedelta(minutes=1)
            return False
        return False

    def _prewarm_targets(self, fn_ref):
        now = time.time()
        seen = set()
        targets = [t.strip() for t in fn_ref.split(',') if t.strip()]
        to_start = []
        with self._lock:
            for target in targets:
                if '@' not in target:
                    continue
                ns = target.split('@')[0]
                if ns in seen:
                    continue
                seen.add(ns)
                if self.services.has(target):
                    continue
                last = self._prewarmed.get(ns, 0)
                if now - last < 30:
                    continue
                self._prewarmed[ns] = now
                to_start.append(ns)
        for ns in to_start:
            self.app.emit('plugins@start', ns, hidden=True)

    @staticmethod
    def _parse_time(time_str):
        parts = (time_str or '00:00').split(':')
        h = int(parts[0]) if len(parts) > 0 else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return h, m, s

    # ===================================================================
    #  fire (runs in thread-pool worker)
    # ===================================================================

    def _fire(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.get('dead'):
                return
            fn_ref = task['fn_ref']
            timeout_val = task.get('timeout', 0) or None

        targets = [t.strip() for t in fn_ref.split(',') if t.strip()]
        if not targets:
            targets = [fn_ref]

        all_ok = True
        results = []
        total_startup_ms = 0
        t0 = time.perf_counter()

        for target in targets:
            ok, result, startup_ms = self._call_target(target, task, timeout_val)
            if not ok:
                all_ok = False
            total_startup_ms += startup_ms
            results.append(f'{target}: {result}')

        elapsed = max(0, time.perf_counter() - t0 - total_startup_ms / 1000.0)

        with self._lock:
            t = self._tasks.get(task_id)
            if not t or t.get('dead'):
                return
            t['count'] += 1
            t['total_dur'] += elapsed
            t['avg_dur'] = t['total_dur'] / t['count']
            if elapsed > t['max_dur']:
                t['max_dur'] = elapsed
            if not all_ok:
                t['errors'] += 1
                t['enabled'] = False
                t['failed'] = True
            else:
                t['failed'] = False
                if t['type'] == 'once':
                    t['fired'] = True
            t['firing'] = False
            t.setdefault('history', []).append({
                'at': time.time(),
                'ok': all_ok,
                'elapsed_ms': int(elapsed * 1000),
                'startup_ms': total_startup_ms,
                'results': results,
            })
            if len(t['history']) > _MAX_HISTORY:
                t['history'] = t['history'][-_MAX_HISTORY:]

        if self.root:
            event = 'task_succeeded' if all_ok else 'task_failed'
            data = {
                'task_id': task_id, 'fn_ref': fn_ref,
                'elapsed_ms': int(elapsed * 1000),
                'startup_ms': total_startup_ms,
            }
            self.root.after(0, lambda e=event, d=data: self.app.emit(e, d))

    def _call_target(self, target, task, timeout_val):
        """Call a single target. Returns (ok, result_str, startup_ms).

        Does NOT mutate *task* — state updates happen under lock in _fire.
        """
        def _call():
            return self.services.call(target)

        ok = False
        result = None
        startup_ms = 0
        try:
            future = self._executor.submit(_call)
            try:
                result = future.result(timeout=timeout_val)
                ok = True
            except concurrent.futures.TimeoutError:
                result = f'timeout({timeout_val}s)'
        except KeyError:
            if task.get('auto_start', True) and '@' in target:
                plugin_ns = target.split('@')[0]
                t_start = time.perf_counter()
                if self.root:
                    self.root.after(0, lambda ns=plugin_ns: self.app.emit('plugins@start', ns, hidden=True))
                time.sleep(0.5)
                startup_ms = int((time.perf_counter() - t_start) * 1000)
                try:
                    future2 = self._executor.submit(_call)
                    try:
                        result = future2.result(timeout=timeout_val)
                        ok = True
                    except concurrent.futures.TimeoutError:
                        result = f'timeout({timeout_val}s)'
                except KeyError:
                    result = 'not found'
            else:
                result = 'not found'
        except Exception as e:
            result = str(e)[:80]

        return ok, str(result)[:80] if result is not None else 'ok', startup_ms

    # ===================================================================
    #  service handlers
    # ===================================================================

    def _require_new_id(self, task_id, updating=False):
        with self._lock:
            if task_id in self._tasks and not updating:
                raise ValueError(f"task_id '{task_id}' already exists")

    @staticmethod
    def _base(typ, fn_ref, **kw):
        return {'type': typ, 'fn_ref': fn_ref,
                'auto_start': kw.get('auto_start', True),
                'max_runs': kw.get('max_runs', 0) or 0,
                'timeout': kw.get('timeout', 0) or 0,
                'enabled': True,
                'last_run': 0, 'count': 0, 'errors': 0,
                'total_dur': 0.0, 'avg_dur': 0.0, 'max_dur': 0.0,
                'history': [],
                'created_at': time.time(), **kw}

    def _add_task(self, task_id, task_data, old_task=None):
        if old_task:
            for key in self._PRESERVE_ON_EDIT:
                if key in old_task:
                    task_data[key] = old_task[key]
        with self._lock:
            self._tasks[task_id] = task_data
        return task_id

    def _every(self, task_id, interval, fn_ref,
               auto_start=True, max_runs=0, timeout=0, updating=False):
        self._require_new_id(task_id, updating=updating)
        extra = {}
        if not updating:
            extra['last_run'] = time.time()
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'every', fn_ref, interval=float(interval),
            auto_start=auto_start, max_runs=max_runs, timeout=timeout, **extra),
            old_task=old)

    def _once(self, task_id, delay, fn_ref, auto_start=True,
              timeout=0, updating=False):
        self._require_new_id(task_id, updating=updating)
        fire_at = self._resolve_once_fire_at(delay)
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'once', fn_ref, delay=str(delay),
            fire_at=fire_at,
            auto_start=auto_start, timeout=timeout), old_task=old)

    @staticmethod
    def _resolve_once_fire_at(delay_str):
        s = str(delay_str).strip()
        try:
            return time.time() + float(s)
        except ValueError:
            pass
        parts = s.split(':')
        if 2 <= len(parts) <= 3 and all(p.isdigit() for p in parts):
            h, m = int(parts[0]), int(parts[1])
            sec = int(parts[2]) if len(parts) > 2 else 0
            now = datetime.now()
            target = now.replace(hour=h, minute=m, second=sec, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target.timestamp()
        raise ValueError(f"Invalid delay value: {delay_str!r}") from None

    def _daily(self, task_id, time_str, fn_ref,
               auto_start=True, max_runs=0, timeout=0, updating=False):
        self._require_new_id(task_id, updating=updating)
        extra = {}
        if not updating:
            h, m, s = self._parse_time(time_str)
            target_secs = h * 3600 + m * 60 + s
            now = datetime.now()
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            if now_secs >= target_secs:
                extra['last_day'] = now.strftime('%Y-%m-%d')
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'daily', fn_ref, time_str=time_str,
            auto_start=auto_start, max_runs=max_runs, timeout=timeout,
            **extra), old_task=old)

    def _weekly(self, task_id, days, time_str, fn_ref,
                auto_start=True, max_runs=0, timeout=0, updating=False):
        self._require_new_id(task_id, updating=updating)
        extra = {}
        if not updating:
            h, m, s = self._parse_time(time_str)
            target_secs = h * 3600 + m * 60 + s
            now = datetime.now()
            now_secs = now.hour * 3600 + now.minute * 60 + now.second
            dow = now.weekday()
            if now_secs >= target_secs or dow not in (days or []):
                extra['last_day'] = now.strftime('%Y-%m-%d')
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'weekly', fn_ref, days=list(days), time_str=time_str,
            auto_start=auto_start, max_runs=max_runs, timeout=timeout,
            **extra), old_task=old)

    def _cron(self, task_id, cron_expr, fn_ref,
              auto_start=True, max_runs=0, timeout=0, updating=False):
        self._require_new_id(task_id, updating=updating)
        extra = {}
        if not updating:
            extra['last_minute'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'cron', fn_ref, cron_expr=cron_expr,
            auto_start=auto_start, max_runs=max_runs, timeout=timeout, **extra),
            old_task=old)

    def _cancel(self, task_id):
        with self._lock:
            r = self._tasks.pop(task_id, None) is not None
            if r:
                self._pre_pause_state.pop(task_id, None)
        return r

    def _skip_to_now(self, t):
        tp = t.get('type')
        now_ts = time.time()
        now_dt = datetime.now()
        if tp == 'every':
            t['last_run'] = now_ts
        elif tp in ('daily', 'weekly'):
            time_str = t.get('time_str', '00:00')
            parts = time_str.split(':')
            h = int(parts[0]) if parts else 0
            m = int(parts[1]) if len(parts) > 1 else 0
            s = int(parts[2]) if len(parts) > 2 else 0
            target = h * 3600 + m * 60 + s
            now_secs = now_dt.hour * 3600 + now_dt.minute * 60 + now_dt.second
            if now_secs >= target:
                t['last_day'] = now_dt.strftime('%Y-%m-%d')
        elif tp == 'cron':
            t['last_minute'] = now_dt.strftime('%Y-%m-%d %H:%M')
        elif tp == 'once':
            if now_ts >= t.get('fire_at', 0):
                t['fired'] = True

    def _resume(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            if t:
                t['enabled'] = True
                t['dead'] = False
                t['failed'] = False
                self._skip_to_now(t)
        return t is not None

    def _pause(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            if t:
                t['enabled'] = False
        return t is not None

    def _toggle_enabled(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return None
            t['enabled'] = not t.get('enabled', True)
            if t['enabled']:
                t['dead'] = False
                t['failed'] = False
                self._skip_to_now(t)
            new_state = t['enabled']
        return new_state

    def _pause_all(self):
        with self._lock:
            for tid, t in self._tasks.items():
                if t.get('enabled', True):
                    self._pre_pause_state[tid] = True
                    t['enabled'] = False
        self._global_paused = True

    def _resume_all(self):
        with self._lock:
            for tid in list(self._pre_pause_state.keys()):
                t = self._tasks.get(tid)
                if t:
                    t['enabled'] = True
                    t['dead'] = False
                    t['failed'] = False
                    self._skip_to_now(t)
            self._pre_pause_state.clear()
        self._global_paused = False

    @property
    def global_paused(self):
        return self._global_paused

    @staticmethod
    def _is_done(task):
        if task.get('fired'):
            return True
        mr = task.get('max_runs', 0)
        return bool(mr and task.get('count', 0) >= mr)

    def _list(self):
        with self._lock:
            return [self._task_info(tid, t) for tid, t in self._tasks.items()]

    def _get(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
        return self._task_info(task_id, t) if t else None

    def _task_info(self, task_id, task):
        return {
            'id': task_id, 'type': task['type'],
            'fn_ref': task['fn_ref'],
            'interval': task.get('interval'),
            'delay': task.get('delay'),
            'time_str': task.get('time_str'),
            'days': task.get('days'),
            'cron_expr': task.get('cron_expr'),
            'enabled': task.get('enabled', True),
            'auto_start': task.get('auto_start', True),
            'max_runs': task.get('max_runs', 0),
            'timeout': task.get('timeout', 0),
            'count': task['count'], 'errors': task['errors'],
            'avg_ms': int(task['avg_dur'] * 1000),
            'max_ms': int(task['max_dur'] * 1000),
            'dead': task.get('dead', False),
            'firing': task.get('firing', False),
            'fired': task.get('fired', False),
            'failed': task.get('failed', False),
            'last_run': task.get('last_run', 0),
            'created_at': task.get('created_at', 0),
            'schedule': _schedule_str(task),
            'history': task.get('history', []),
        }

    def on_stop(self):
        with self._lock:
            for t in self._tasks.values():
                t['firing'] = False
        if self._executor:
            self._executor.shutdown(wait=False)
