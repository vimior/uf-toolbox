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
import json
import os
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
                         'max_dur', 'history', 'last_run', 'last_fired',
                         'created_at')

    def __init__(self, app=None):
        super().__init__(app)
        self._tasks = {}
        self._lock = threading.RLock()
        self._global_paused = False
        self._pre_pause_state = {}
        self._prewarmed = {}
        self._tasks_path = os.path.join(self.root.config_dir, 'tasks.json')

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
        s.register('restart', self._restart)

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
        self._load()
        self._start_tick()

    # ===================================================================
    #  persistence
    # ===================================================================

    def _save(self):
        if not os.path.isabs(self._tasks_path):
            return  # mock path, skip
        with self._lock:
            data = {tid: {k: v for k, v in t.items()
                          if k not in ('firing',)}
                    for tid, t in self._tasks.items()}
        try:
            os.makedirs(os.path.dirname(self._tasks_path), exist_ok=True)
            tmp = self._tasks_path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'tasks': data, 'updated_at': time.strftime('%Y-%m-%d %H:%M:%S')}, f)
            os.replace(tmp, self._tasks_path)
        except Exception:
            import traceback
            traceback.print_exc()

    def _load(self):
        if not os.path.exists(self._tasks_path):
            return
        try:
            with open(self._tasks_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return
        for tid, t in (data.get('tasks') or {}).items():
            t.setdefault('enabled', True)
            t.pop('firing', None)
            t.pop('dead', None)
            t.pop('failed', None)
            # 不做 last_run 覆盖: _skip_to_now 会对 every 无 start_time 的
            # 任务对齐到最近过去槽位 (跳过过期周期, 保持原相位, 不立即触发)
            self._tasks[tid] = t
            self._skip_to_now(t)

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
            self.root.after(100, self._tick)

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
                            t['last_fired'] = now_ts
                            fire = True
                if fire:
                    self._executor.submit(self._fire, task_id)

    def _should_fire(self, task, now, now_ts):
        tp = task['type']
        if tp == 'every':
            if task.get('start_time'):
                if now_ts < task['start_time']:
                    return False
                first_slot = task['start_time'] + task['interval']
                if now_ts < first_slot:
                    return False
                base = max(task['last_run'], task['start_time'])
                k = int((base - task['start_time']) / task['interval']) + 1
                next_slot = task['start_time'] + k * task['interval']
                return now_ts >= next_slot
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
            if task.get('start_time'):
                if now_ts < task['start_time']:
                    return False
                first_slot = task['start_time'] + task['interval']
                if now_ts < first_slot:
                    return first_slot - now_ts <= seconds
                base = max(task['last_run'], task['start_time'])
                k = int((base - task['start_time']) / task['interval']) + 1
                next_slot = task['start_time'] + k * task['interval']
                return next_slot - now_ts <= seconds
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

    @staticmethod
    def _resolve_start_time(value):
        """Resolve *value* to a Unix timestamp (float).

        Accepted formats
        ----------------
        - int / float  →  Unix timestamp (used directly)
        - ``"YYYY-MM-DD HH:MM:SS"``  →  absolute datetime
        - ``"HH:MM:SS"`` or ``"HH:MM"``  →  today at that time (past is valid)
        - ``None``  →  returns ``None``
        """
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        # absolute datetime: "2026-07-30 14:30:00"
        try:
            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').timestamp()
        except ValueError:
            pass
        # time string: "HH:MM:SS" or "HH:MM"
        parts = s.split(':')
        if 2 <= len(parts) <= 3 and all(p.isdigit() for p in parts):
            h, m = int(parts[0]), int(parts[1])
            sec = int(parts[2]) if len(parts) > 2 else 0
            return datetime.now().replace(
                hour=h, minute=m, second=sec, microsecond=0).timestamp()
        raise ValueError(f"Invalid start_time: {value!r}") from None

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
                    t['enabled'] = False
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
            self._save()  # 执行结果落盘, 重启后不丢失

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
            task_args = task.get('args', ())
            task_kwargs = task.get('kwargs', {})
            return self.services.call(target, *task_args, **task_kwargs)

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
            import traceback
            traceback.print_exc()
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
    def _base(typ, fn_ref, args=(), kwargs=None, **kw):
        return {'type': typ, 'fn_ref': fn_ref,
                'auto_start': kw.get('auto_start', True),
                'max_runs': kw.get('max_runs', 0) or 0,
                'timeout': kw.get('timeout', 0) or 0,
                'enabled': True,
                'last_run': 0, 'last_fired': 0, 'count': 0, 'errors': 0,
                'total_dur': 0.0, 'avg_dur': 0.0, 'max_dur': 0.0,
                'args': tuple(args), 'kwargs': dict(kwargs or {}),
                'history': [],
                'created_at': time.time(), **kw}

    def _add_task(self, task_id, task_data, old_task=None):
        if old_task:
            for key in self._PRESERVE_ON_EDIT:
                if key in old_task:
                    task_data[key] = old_task[key]
            # editing revives a failed/dead/disabled task
            if old_task.get('failed') or old_task.get('dead') or not old_task.get('enabled', True):
                task_data['failed'] = False
                task_data['dead'] = False
                task_data['enabled'] = True
                if old_task.get('failed') or old_task.get('dead'):
                    # failure/dead → reset timer
                    if old_task.get('type') == 'once':
                        task_data['fired'] = False
                        task_data['fire_at'] = self._resolve_once_fire_at(
                            task_data.get('delay', '0'))
                    elif old_task.get('type') == 'every':
                        task_data['last_run'] = time.time()
                else:
                    # just paused → preserve cadence
                    self._skip_to_now(task_data)
        with self._lock:
            self._tasks[task_id] = task_data
        self._save()
        return task_id

    def _every(self, task_id, interval, fn_ref,
               auto_start=True, max_runs=0, timeout=0, updating=False,
               args=(), kwargs=None, start_time=None):
        self._require_new_id(task_id, updating=updating)
        extra = {}
        if not updating:
            extra['last_run'] = time.time()
        if start_time is not None:
            extra['start_time'] = self._resolve_start_time(start_time)
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'every', fn_ref, args=args, kwargs=kwargs,
            interval=float(interval),
            auto_start=auto_start, max_runs=max_runs, timeout=timeout, **extra),
            old_task=old)

    def _once(self, task_id, delay, fn_ref, auto_start=True,
              timeout=0, updating=False, args=(), kwargs=None):
        self._require_new_id(task_id, updating=updating)
        fire_at = self._resolve_once_fire_at(delay)
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'once', fn_ref, args=args, kwargs=kwargs,
            delay=str(delay), fire_at=fire_at,
            auto_start=auto_start, timeout=timeout), old_task=old)

    @staticmethod
    def _resolve_once_fire_at(delay_value):
        s = str(delay_value).strip()
        # absolute datetime: "2026-07-30 14:30:00"
        try:
            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S').timestamp()
        except ValueError:
            pass
        # time string: "HH:MM:SS" or "HH:MM"
        parts = s.split(':')
        if 2 <= len(parts) <= 3 and all(p.isdigit() for p in parts):
            h, m = int(parts[0]), int(parts[1])
            sec = int(parts[2]) if len(parts) > 2 else 0
            now = datetime.now()
            target = now.replace(hour=h, minute=m, second=sec, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target.timestamp()
        # numeric: always relative seconds (use datetime string for absolute times)
        try:
            return time.time() + float(s)
        except ValueError:
            pass
        raise ValueError(f"Invalid delay value: {delay_value!r}") from None

    def _daily(self, task_id, time_str, fn_ref,
               auto_start=True, max_runs=0, timeout=0, updating=False,
               args=(), kwargs=None):
        self._require_new_id(task_id, updating=updating)
        h, m, s = self._parse_time(time_str)
        target_secs = h * 3600 + m * 60 + s
        now = datetime.now()
        now_secs = now.hour * 3600 + now.minute * 60 + now.second
        extra = {}
        if now_secs >= target_secs:
            extra['last_day'] = now.strftime('%Y-%m-%d')
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'daily', fn_ref, args=args, kwargs=kwargs,
            time_str=time_str,
            auto_start=auto_start, max_runs=max_runs, timeout=timeout,
            **extra), old_task=old)

    def _weekly(self, task_id, days, time_str, fn_ref,
                auto_start=True, max_runs=0, timeout=0, updating=False,
                args=(), kwargs=None):
        self._require_new_id(task_id, updating=updating)
        h, m, s = self._parse_time(time_str)
        target_secs = h * 3600 + m * 60 + s
        now = datetime.now()
        now_secs = now.hour * 3600 + now.minute * 60 + now.second
        dow = now.weekday()
        extra = {}
        if now_secs >= target_secs or dow not in (days or []):
            extra['last_day'] = now.strftime('%Y-%m-%d')
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'weekly', fn_ref, args=args, kwargs=kwargs,
            days=list(days), time_str=time_str,
            auto_start=auto_start, max_runs=max_runs, timeout=timeout,
            **extra), old_task=old)

    def _cron(self, task_id, cron_expr, fn_ref,
              auto_start=True, max_runs=0, timeout=0, updating=False,
              args=(), kwargs=None):
        self._require_new_id(task_id, updating=updating)
        extra = {'last_minute': datetime.now().strftime('%Y-%m-%d %H:%M')}
        old = self._tasks.get(task_id) if updating else None
        return self._add_task(task_id, self._base(
            'cron', fn_ref, args=args, kwargs=kwargs,
            cron_expr=cron_expr,
            auto_start=auto_start, max_runs=max_runs, timeout=timeout, **extra),
            old_task=old)

    def _cancel(self, task_id):
        with self._lock:
            r = self._tasks.pop(task_id, None) is not None
            if r:
                self._pre_pause_state.pop(task_id, None)
                self._save()
        return r

    def _skip_to_now(self, t):
        tp = t.get('type')
        now_ts = time.time()
        now_dt = datetime.now()
        if tp == 'every':
            if t.get('start_time'):
                t['last_run'] = now_ts  # grid logic handles alignment
            elif t.get('last_run', 0) > 0:
                elapsed = now_ts - t['last_run']
                periods = int(elapsed / t['interval'])
                if periods > 0:
                    t['last_run'] += periods * t['interval']
            else:
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
                was_failed = t.get('failed')
                t['enabled'] = True
                t['dead'] = False
                t['failed'] = False
                if was_failed:
                    # failure → reset timer, start fresh
                    if t.get('type') == 'once':
                        t['fired'] = False
                        t['fire_at'] = self._resolve_once_fire_at(
                            t.get('delay', '0'))
                    elif t.get('type') == 'every':
                        t['last_run'] = time.time()
                else:
                    # normal pause → preserve cadence
                    self._skip_to_now(t)
                self._save()
        return t is not None

    def _pause(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            if t:
                t['enabled'] = False
                self._save()
        return t is not None

    def _restart(self, task_id):
        """完成的任务重新执行: 清零执行计数并恢复启用, 重建计时.

        *history* 保留 (历史执行记录不清); once 重新解析 fire_at.
        """
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return False
            t['count'] = 0
            t['errors'] = 0
            t['total_dur'] = 0.0
            t['avg_dur'] = 0.0
            t['max_dur'] = 0.0
            t['enabled'] = True
            t['failed'] = False
            t['dead'] = False
            if t.get('type') == 'once':
                t['fired'] = False
                t['fire_at'] = self._resolve_once_fire_at(t.get('delay', '0'))
            else:
                self._skip_to_now(t)
            self._save()
        return True

    def _toggle_enabled(self, task_id):
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return None
            t['enabled'] = not t.get('enabled', True)
            if t['enabled']:
                was_failed = t.get('failed')
                t['dead'] = False
                t['failed'] = False
                if was_failed:
                    if t.get('type') == 'once':
                        t['fired'] = False
                        t['fire_at'] = self._resolve_once_fire_at(
                            t.get('delay', '0'))
                    elif t.get('type') == 'every':
                        t['last_run'] = time.time()
                else:
                    self._skip_to_now(t)
                self._save()
            new_state = t['enabled']
        return new_state

    def _pause_all(self):
        with self._lock:
            for tid, t in self._tasks.items():
                if t.get('enabled', True):
                    self._pre_pause_state[tid] = True
                    t['enabled'] = False
        self._global_paused = True
        self._save()

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
        self._save()

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
            'start_time': task.get('start_time'),
            'enabled': task.get('enabled', True),
            'auto_start': task.get('auto_start', True),
            'max_runs': task.get('max_runs', 0),
            'timeout': task.get('timeout', 0),
            'args': task.get('args', ()),
            'kwargs': task.get('kwargs', {}),
            'count': task['count'], 'errors': task['errors'],
            'avg_ms': int(task['avg_dur'] * 1000),
            'max_ms': int(task['max_dur'] * 1000),
            'dead': task.get('dead', False),
            'firing': task.get('firing', False),
            'fired': task.get('fired', False),
            'failed': task.get('failed', False),
            'last_run': task.get('last_run', 0),
            'last_fired': task.get('last_fired', 0),
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
