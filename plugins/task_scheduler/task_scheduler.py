# -*- coding: utf-8 -*-
"""Task Scheduler panel — GuiPlugin, pure UI management.

Requires TasksService (task_service.py) to be running at the app level.
Communicates via services: tasks@list, tasks@get, tasks@create_*, etc.
"""
import time
import tkinter as tk
from tkinter import ttk

from plugins.plugin import GuiPlugin
from plugins.plugin_guide.plugin_guide import PluginGuide

# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

from plugins.task_scheduler._cron_utils import (
    _WEEKDAY_NAMES,
    validate_cron,
    next_cron_runs,
)

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

_LANG = {
    'zh': {
        'title':           '任务调度器',
        'no_tasks':        '暂无任务',
        'add_task':        '+ 新建',
        'pause_all':       '全部暂停',
        'resume_all':      '全部恢复',
        'status_failed':   '失败',
        'col_id':          'ID',
        'col_type':        '类型',
        'col_last':        '上次执行',
        'col_status':      '状态',
        'status_active':   '活跃',
        'status_dead':     '失效',
        'status_off':      '停用',
        'status_running':  '运行中',
        'status_done':     '完成',
        'edit_task':       '编辑任务',
        'add_task_title':  '新建任务',
        'form_target':     '目标服务',
        'form_task_id':    '任务 ID',
        'form_type':       '类型',
        'form_interval':   '间隔 (秒)',
        'form_delay':      '延迟 (秒)',
        'form_at':         '指定时间',
        'form_time':       '时间',
        'form_days':       '星期',
        'form_cron':       'Cron 表达式',
        'form_target_hint': '格式: 命名空间@方法名\n多个用逗号分隔, 例如: demo@hello, demo@bye',
        'form_auto_start': '目标离线时自动启动',
        'form_max_runs':   '最大执行次数',
        'form_cancel':     '取消',
        'form_save':       '保存',
        'form_validate_id':      '请输入任务 ID',
        'form_validate_target':  '请输入目标服务',
        'form_validate_interval': '间隔必须为正数',
        'form_validate_delay':    '请输入秒数或时间 (如 60 或 14:30)',
        'form_validate_cron':     'Cron 表达式无效',
        'form_validate_number':   '最大执行次数必须为整数',
        'form_validate_dup':      '任务 ID 已存在，请换一个',
        'form_validate_days':     '请至少选择一天',
        'form_next':       '下次: ',
        'form_invalid':    '(无效)',
    },
    'en': {
        'title':           'Task Scheduler',
        'no_tasks':        'No tasks',
        'add_task':        '+ Add',
        'pause_all':       'Pause All',
        'resume_all':      'Resume All',
        'status_failed':   'failed',
        'col_id':          'ID',
        'col_type':        'Type',
        'col_last':        'Last Run',
        'col_status':      'Status',
        'status_active':   'active',
        'status_dead':     'dead',
        'status_off':      'off',
        'status_running':  'running',
        'status_done':     'done',
        'edit_task':       'Edit Task',
        'add_task_title':  'Add Task',
        'form_target':     'Target',
        'form_task_id':    'Task ID',
        'form_type':       'Type',
        'form_interval':   'Interval (s)',
        'form_delay':      'Delay (s)',
        'form_at':         'At Time',
        'form_time':       'Time',
        'form_days':       'Days',
        'form_cron':       'Cron',
        'form_target_hint': 'Format: namespace@method\nComma-separated for multiple, e.g: demo@hello, demo@bye',
        'form_auto_start': 'Auto-start plugin if offline',
        'form_max_runs':   'Max runs',
        'form_cancel':     'Cancel',
        'form_save':       'Save',
        'form_validate_id':      'Task ID is required',
        'form_validate_target':  'Target is required',
        'form_validate_interval': 'Interval must be a positive number',
        'form_validate_delay':    'Enter seconds or time (e.g. 60 or 14:30)',
        'form_validate_cron':     'Invalid cron expression',
        'form_validate_number':   'Max runs must be an integer',
        'form_validate_dup':      'Task ID already exists',
        'form_validate_days':     'Select at least one day',
        'form_next':       'Next: ',
        'form_invalid':    '(invalid)',
    },
}

# ---------------------------------------------------------------------------
# theme
# ---------------------------------------------------------------------------

_STYLE = {
    'dark': {
        'bg':        '#2b2b2b',
        'bar':       '#333333',
        'card':      '#363636',
        'fg':        '#e0e0e0',
        'hint':      '#888888',
        'hover':     '#4a4a4a',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
        'dead':      '#d94a4a',
        'sep':       '#3c3c3c',
    },
    'light': {
        'bg':        '#f5f5f5',
        'bar':       '#e0e0e0',
        'card':      '#ffffff',
        'fg':        '#333333',
        'hint':      '#999999',
        'hover':     '#d0d0d0',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
        'dead':      '#c0392b',
        'sep':       '#d0d0d0',
    },
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_time_picker(parent, initial=''):
    f = tk.Frame(parent, bg=parent['bg'])
    parts = initial.split(':') if initial else ['', '']
    h = parts[0] if len(parts) > 0 and parts[0].isdigit() else '00'
    m = parts[1] if len(parts) > 1 and parts[1].isdigit() else '00'
    s = parts[2] if len(parts) > 2 and parts[2].isdigit() else '00'
    hours = [f'{i:02d}' for i in range(24)]
    mins = [f'{i:02d}' for i in range(60)]
    secs = [f'{i:02d}' for i in range(60)]
    h_var = tk.StringVar(value=h)
    ttk.Combobox(f, textvariable=h_var, values=hours,
                 font=('Consolas', 9), width=3, state='readonly').pack(side=tk.LEFT)
    tk.Label(f, text=':', font=('Consolas', 9), bg=parent['bg'],
             fg='#888').pack(side=tk.LEFT)
    m_var = tk.StringVar(value=m)
    ttk.Combobox(f, textvariable=m_var, values=mins,
                 font=('Consolas', 9), width=3, state='readonly').pack(side=tk.LEFT)
    tk.Label(f, text=':', font=('Consolas', 9), bg=parent['bg'],
             fg='#888').pack(side=tk.LEFT)
    s_var = tk.StringVar(value=s)
    ttk.Combobox(f, textvariable=s_var, values=secs,
                 font=('Consolas', 9), width=3, state='readonly').pack(side=tk.LEFT)
    f.pack(side=tk.LEFT, padx=4)
    return lambda: f'{h_var.get()}:{m_var.get()}:{s_var.get()}'


# ---------------------------------------------------------------------------
# panel
# ---------------------------------------------------------------------------

class TaskScheduler(GuiPlugin):
    name = 'Task Scheduler'
    name_zh = '任务调度器'
    name_en = 'Task Scheduler'
    namespace = 'task_panel'
    priority = 997
    reload = True
    fixed_position = True
    fixed_size = False

    _GROUP_ORDER = ('active', 'failed', 'off', 'done')

    def __init__(self, parent=None, app=None):
        super().__init__(parent, app)

        lang_name = self.app.current_lang_name
        theme_name = self.app.current_theme_name
        self._l = _LANG.get(lang_name, _LANG['en'])
        self._s = _STYLE.get(theme_name, _STYLE['dark'])
        s = self._s
        l = self._l

        self.title(l['title'])
        self.resizable(True, True)
        self.minsize(666, 520)
        self.configure(bg=s['bg'])

        self._rows = {}
        self._expanded = set()
        self._detail_frames = {}
        self._help_win = None
        self._form_win = None

        # ---- toolbar ----
        bar = tk.Frame(self, bg=s['bar'], height=34)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        self._status_lbl = tk.Label(bar, text='', font=('Consolas', 10),
                                     bg=s['bar'], fg=s['hint'])
        self._status_lbl.pack(side=tk.LEFT, padx=10, pady=6)

        self._pause_btn = tk.Label(bar, text=l['pause_all'],
                                    bg=s['bar'], fg=s['fg'],
                                    font=('Consolas', 10),
                                    cursor='hand2', padx=8)
        self._pause_btn.bind('<Button-1>', lambda e: self._toggle_global_pause())
        self._pause_btn.bind('<Enter>', lambda e: self._pause_btn.config(bg=s['hover']))
        self._pause_btn.bind('<Leave>', lambda e: self._pause_btn.config(bg=s['bar']))
        self._pause_btn.pack(side=tk.RIGHT, padx=2, pady=5)

        for text, cmd in [
            (l['add_task'], self._show_form),
            ('?', self._show_help),
        ]:
            lbl = tk.Label(bar, text=text, bg=s['bar'], fg=s['fg'],
                           font=('Consolas', 10), cursor='hand2', padx=8)
            lbl.bind('<Button-1>', lambda e, c=cmd: c())
            lbl.bind('<Enter>', lambda e, b=lbl: b.config(bg=s['hover']))
            lbl.bind('<Leave>', lambda e, b=lbl: b.config(bg=s['bar']))
            lbl.pack(side=tk.RIGHT, padx=2, pady=5)

        # ---- table header ----
        hdr = tk.Frame(self, bg=s['bar'])
        hdr.pack(fill=tk.X, side=tk.TOP, padx=4, pady=(2, 0))
        hdr_lbls = [l['col_id'], l['col_type'], l['col_last'], l['col_status']]
        hdr_widths = (45, 6, None, 6)
        for label, w in zip(hdr_lbls, hdr_widths):
            kw = {'width': w} if w else {}
            tk.Label(hdr, text=label, font=('Consolas', 10, 'bold'),
                     bg=s['bar'], fg=s['hint'], anchor='w',
                     **kw).pack(side=tk.LEFT, padx=1,
                                fill=tk.X if w is None else tk.NONE,
                                expand=w is None)
        tk.Label(hdr, text='', font=('Consolas', 1),
                 bg=s['bar'], width=12).pack(side=tk.RIGHT)

        tk.Frame(self, bg=s['hint'], height=1).pack(fill=tk.X, padx=4)

        # ---- scrollable content ----
        scroll_frame = tk.Frame(self, bg=s['bg'])
        scroll_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self._canvas = tk.Canvas(scroll_frame, bg=s['bg'], highlightthickness=0)
        self._scrollbar = tk.Scrollbar(scroll_frame, orient=tk.VERTICAL, width=8,
                                       command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg=s['bg'])
        self._canvas.create_window((0, 0), window=self._inner, anchor='nw',
                                   tags=('inner',))
        self._canvas.bind('<Configure>',
                          lambda e: self._canvas.itemconfig('inner', width=e.width),
                          '+')

        def _on_inner_configure(_):
            bbox = self._canvas.bbox('all')
            if bbox:
                x1, y1, x2, y2 = bbox
                pad = 5
                self._canvas.configure(scrollregion=(x1, y1, x2, y2 + pad))
        self._inner.bind('<Configure>', _on_inner_configure)
        # Bind on the panel window so MouseWheel works even over child widgets
        self.bind('<MouseWheel>',
                  lambda e: self._canvas.yview_scroll(
                      int(-e.delta / 120), 'units'))

        self._empty = tk.Label(self._inner, text=l['no_tasks'],
                               font=('Consolas', 10), bg=s['bg'], fg=s['hint'])
        self._empty.pack(pady=30)

        # ---- start refresh loop ----
        self._rebuild_ui()
        self._tick_refresh()

    # ===================================================================
    #  service helpers
    # ===================================================================

    def _srv(self, name, *args, **kw):
        try:
            return self.app.services.call(f'tasks@{name}', *args, **kw)
        except KeyError:
            return None

    def _all_tasks(self):
        items = self._srv('list')
        if not items:
            return {}
        return {t['id']: t for t in items}

    # ===================================================================
    #  refresh loop
    # ===================================================================

    def _tick_refresh(self):
        if self.winfo_exists():
            self._refresh_display()
            self._status_lbl.config(text=time.strftime('%H:%M:%S'))
            self.after(1000, self._tick_refresh)

    # ===================================================================
    #  UI — rebuild / refresh
    # ===================================================================

    @staticmethod
    def _is_done(task):
        if task.get('fired'):
            return True
        mr = task.get('max_runs', 0)
        return bool(mr and task.get('count', 0) >= mr)

    def _status_text(self, task):
        if task.get('dead'):
            return self._l['status_dead']
        if task.get('failed'):
            return self._l['status_failed']
        if self._is_done(task):
            return self._l['status_done']
        if not task.get('enabled', True):
            return self._l['status_off']
        if task.get('firing'):
            return self._l['status_running']
        return self._l['status_active']

    def _task_group(self, task):
        """Return the group key for *task*."""
        if self._is_done(task):
            return 'done'
        if task.get('failed'):
            return 'failed'
        if not task.get('enabled', True):
            return 'off'
        return 'active'

    def _group_title(self, key, count):
        labels = {
            'active': self._l['status_active'],
            'failed': self._l['status_failed'],
            'off':    self._l['status_off'],
            'done':   self._l['status_done'],
        }
        return f'── {labels.get(key, key)} ({count}) ' + '─' * 30

    def _rebuild_ui(self):
        for w in self._inner.winfo_children():
            if w is not self._empty:
                w.destroy()
        self._rows.clear()
        self._detail_frames.clear()
        self._expanded.clear()

        tasks = self._all_tasks()
        if not tasks:
            self._empty.pack(pady=30)
            return

        self._empty.pack_forget()
        s = self._s

        grouped = {k: [] for k in self._GROUP_ORDER}
        for tid, task in tasks.items():
            grouped[self._task_group(task)].append((tid, task))

        first = True
        for key in self._GROUP_ORDER:
            items = grouped.get(key, [])
            if not items:
                continue
            if not first:
                tk.Frame(self._inner, bg=s['hint'], height=1).pack(
                    fill=tk.X, padx=8, pady=(6, 2))
            first = False
            tk.Label(self._inner, text=self._group_title(key, len(items)),
                     font=('Consolas', 9, 'bold'),
                     bg=s['bg'], fg=s['hint'], anchor='w').pack(
                fill=tk.X, padx=8, pady=(2, 1))

            for tid, task in sorted(items, key=lambda x: x[0]):
                self._add_row(tid, task, s)

    def _add_row(self, tid, task, s):
        dead = task.get('dead')
        failed = task.get('failed')
        disabled = not task.get('enabled', True)
        is_done = self._is_done(task)

        row = tk.Frame(self._inner, bg=s['card'])
        row.pack(fill=tk.X, padx=4, pady=1)

        if dead or failed:
            fg = s['dead']
        elif disabled or is_done:
            fg = s['hint']
        elif task.get('firing'):
            fg = s['accent']
        else:
            fg = s['fg']

        last_str = '-' if not task.get('last_run') else \
                   time.strftime('%m-%d %H:%M:%S', time.localtime(task['last_run']))
        vals = [tid, task['type'], last_str, self._status_text(task)]

        row.bind('<Button-1>', lambda e, t=tid: self._toggle_expand(t))
        lbls = []
        widths = (45, 6, None, 6)
        for v, w in zip(vals, widths):
            kw = {'width': w} if w else {}
            lbl = tk.Label(row, text=str(v)[:30], font=('Consolas', 10),
                           bg=s['card'], fg=fg, anchor='w', **kw)
            lbl.pack(side=tk.LEFT, padx=1, fill=tk.X if w is None else tk.NONE,
                     expand=w is None)
            lbl.bind('<Button-1>', lambda e, t=tid: self._toggle_expand(t))
            lbls.append(lbl)

        # edit
        def _edit_cmd(t=tid):
            self._show_form(t)
        tk.Button(row, text='✎', command=_edit_cmd,
                  font=('Consolas', 10), width=2,
                  bg=s['card'], fg=s['fg'], relief=tk.FLAT, padx=0,
                  activebackground=s['card'], activeforeground=s['accent'],
                  bd=0, cursor='hand2').pack(side=tk.RIGHT, padx=3)

        # pause / play
        if is_done:
            pause_btn = tk.Label(row, text='✓', font=('Consolas', 10),
                                  width=2, bg=s['card'], fg=s['hint'])
        else:
            pause_text = '▶' if (disabled or failed) else '⏸'
            pause_fg = s['hint'] if (disabled or failed) else s['fg']
            pause_btn = tk.Button(row, text=pause_text,
                      command=lambda t=tid: self._do_toggle(t),
                      font=('Consolas', 10), width=2,
                      bg=s['card'], fg=pause_fg, relief=tk.FLAT, padx=0,
                      activebackground=s['card'], activeforeground=s['hint'],
                      bd=0, cursor='hand2')
        pause_btn.pack(side=tk.RIGHT, padx=3)

        # cancel
        tk.Button(row, text='×',
                  command=lambda t=tid: self._do_cancel(t),
                  font=('Consolas', 10), width=2,
                  bg=s['card'], fg=s['dead'], relief=tk.FLAT, padx=0,
                  activebackground=s['card'], activeforeground='#ff6666',
                  bd=0, cursor='hand2').pack(side=tk.RIGHT, padx=3)

        self._rows[tid] = {'labels': lbls, 'pause_btn': pause_btn,
                           'row': row, 'fg': fg, 'group': self._task_group(task)}

    def _do_toggle(self, tid):
        item = self._srv('get', tid)
        if not item:
            return
        if item.get('enabled'):
            self._srv('pause', tid)
        else:
            self._srv('resume', tid)
        self._rebuild_ui()

    def _do_cancel(self, tid):
        self._srv('cancel', tid)
        self._rebuild_ui()

    def _toggle_global_pause(self):
        if self._pause_btn.cget('text') == self._l['pause_all']:
            for t in self._all_tasks().values():
                if t.get('enabled'):
                    self._srv('pause', t['id'])
            self._pause_btn.config(text=self._l['resume_all'])
        else:
            for t in self._all_tasks().values():
                if not t.get('enabled') and not t.get('failed'):
                    self._srv('resume', t['id'])
            self._pause_btn.config(text=self._l['pause_all'])
        self._rebuild_ui()

    def _refresh_display(self):
        s = self._s
        tasks = self._all_tasks()
        task_ids = set(tasks.keys())
        row_ids = set(self._rows.keys())

        # Tasks appeared, disappeared, or changed group — rebuild
        if task_ids != row_ids:
            self._rebuild_ui()
            return
        for tid, task in tasks.items():
            if self._task_group(task) != self._rows[tid].get('group'):
                self._rebuild_ui()
                return

        for tid, task in tasks.items():
            row_data = self._rows.get(tid)
            if not row_data:
                continue
            lbls = row_data['labels']
            pause_btn = row_data.get('pause_btn')
            dead = task.get('dead')
            failed = task.get('failed')
            disabled = not task.get('enabled', True)
            is_done = self._is_done(task)

            if dead or failed:
                fg = s['dead']
            elif disabled or is_done:
                fg = s['hint']
            elif task.get('firing'):
                fg = s['accent']
            else:
                fg = s['fg']

            last_str = '-' if not task.get('last_run') else \
                       time.strftime('%m-%d %H:%M:%S', time.localtime(task['last_run']))
            vals = [tid, task['type'], last_str, self._status_text(task)]
            for lbl, v in zip(lbls, vals):
                lbl.config(text=str(v)[:30], fg=fg)

            if pause_btn and not is_done:
                if disabled or failed:
                    pause_btn.config(text='▶', fg=s['hint'])
                else:
                    pause_btn.config(text='⏸', fg=s['fg'])

            if tid in self._expanded:
                self._refresh_detail(tid)

    # ===================================================================
    #  detail panel
    # ===================================================================

    def _toggle_expand(self, tid):
        if tid in self._expanded:
            self._expanded.discard(tid)
            refs = self._detail_frames.pop(tid, None)
            if refs:
                refs['frame'].destroy()
        else:
            self._expanded.add(tid)
            self._build_detail(tid)

    def _build_detail(self, tid):
        item = self._srv('get', tid)
        if not item:
            return
        row_data = self._rows.get(tid)
        if not row_data:
            return
        row = row_data['row']

        s = self._s
        df = tk.Frame(self._inner, bg=s['card'])
        df.pack(fill=tk.X, padx=4, pady=(0, 2), after=row)

        # line 1: Target header + created
        header = tk.Frame(df, bg=s['bg'])
        header.pack(fill=tk.X, padx=12, pady=(4, 0))
        target_lbl = tk.Label(header, text='Target:', font=('Consolas', 8, 'bold'),
                              bg=s['bg'], fg=s['fg'], anchor='w')
        target_lbl.pack(side=tk.LEFT)
        created_lbl = tk.Label(header, font=('Consolas', 8), bg=s['bg'],
                                fg=s['hint'], anchor='w')
        created_lbl.pack(side=tk.RIGHT)

        # line 2: per-target services (always shown)
        targets_frame = tk.Frame(df, bg=s['bg'])
        targets_lbls = []

        # line 3: per-target results (only after execution)
        results_frame = tk.Frame(df, bg=s['bg'])
        results_lbls = []

        # line 3: stats
        stats_frame = tk.Frame(df, bg=s['bg'])
        stats_lbl = tk.Label(stats_frame, font=('Consolas', 8), bg=s['bg'],
                              fg=s['hint'], anchor='w')
        stats_lbl.pack(side=tk.LEFT)

        # line 4: config
        config_frame = tk.Frame(df, bg=s['bg'])
        config_lbl = tk.Label(config_frame, font=('Consolas', 8), bg=s['bg'],
                               fg=s['hint'], anchor='w')
        config_lbl.pack(side=tk.LEFT)

        self._detail_frames[tid] = {
            'frame': df,
            'target_lbl': target_lbl,
            'created_lbl': created_lbl,
            'targets_frame': targets_frame,
            'targets_lbls': targets_lbls,
            'results_frame': results_frame,
            'results_lbls': results_lbls,
            'stats_frame': stats_frame,
            'stats_lbl': stats_lbl,
            'config_frame': config_frame,
            'config_lbl': config_lbl,
        }
        self._refresh_detail(tid)

    def _refresh_detail(self, tid):
        item = self._srv('get', tid)
        if not item:
            return
        refs = self._detail_frames.get(tid)
        if not refs:
            return

        refs['target_lbl'].config(text='Target:')
        created = time.strftime('%Y-%m-%d %H:%M:%S',
                                time.localtime(item.get('created_at', 0)))
        refs['created_lbl'].config(text=f'Created: {created}')

        # ---- per-target services (hidden when results are available) ----
        hist = item.get('history', [])
        has_results = bool(hist and hist[-1].get('results'))
        tframe = refs['targets_frame']
        tlbls = refs['targets_lbls']
        for lbl in tlbls:
            lbl.destroy()
        tlbls.clear()
        if not has_results:
            targets = [t.strip() for t in item['fn_ref'].split(',') if t.strip()]
            if targets:
                tframe.pack(fill=tk.X, padx=12, pady=(0, 0))
                for t in targets:
                    lbl = tk.Label(tframe, text=f'  {t}', font=('Consolas', 8),
                                   bg=self._s['bg'], fg=self._s['hint'], anchor='w')
                    lbl.pack(fill=tk.X)
                    tlbls.append(lbl)
            else:
                tframe.pack_forget()
        else:
            tframe.pack_forget()

        last = time.strftime('%Y-%m-%d %H:%M:%S',
                             time.localtime(item['last_run'])) \
               if item['last_run'] else '-'
        stats = [
            f'Last: {last}',
            f'×{item["count"]}',
            f'Err: {item["errors"]}',
            f'Avg: {item["avg_ms"]}ms',
            f'Max: {item["max_ms"]}ms',
        ]
        tp = item['type']
        if tp == 'once':
            dly = str(item.get('delay', '?'))
            try:
                float(dly)
                stats.append(f'Delay: {dly}s')
            except ValueError:
                stats.append(f'At: {dly}')
        elif tp == 'every':
            stats.append(f'Interval: {item.get("interval", "?")}s')
        elif tp == 'daily':
            stats.append(f'At: {item.get("time_str", "?")}')
        elif tp == 'weekly':
            days = item.get('days') or []
            ds = ''.join(_WEEKDAY_NAMES[d][:2] for d in sorted(days)) if days else '?'
            stats.append(f'Days: {ds} @ {item.get("time_str", "?")}')
        elif tp == 'cron':
            stats.append(f'Cron: {item.get("cron_expr", "?")}')
        if item.get('timeout'):
            stats.append(f'Timeout: {item["timeout"]}s')

        hist = item.get('history', [])
        if hist:
            last_entry = hist[-1]
            if last_entry.get('startup_ms'):
                stats.append(f'Startup: {last_entry["startup_ms"]}ms')
        refs['stats_lbl'].config(text='  '.join(stats))
        refs['stats_frame'].pack(fill=tk.X, padx=12, pady=(0, 2))

        config = []
        task_args = item.get('args')
        if task_args:
            config.append(f'Args: {", ".join(task_args)}')
        task_kwargs = item.get('kwargs')
        if task_kwargs:
            config.append(f'Kwargs: {", ".join(f"{k}={v}" for k, v in task_kwargs.items())}')
        if item.get('max_runs'):
            config.append(f'Max runs: {item["max_runs"]}')
        if item.get('timeout'):
            config.append(f'Timeout: {item["timeout"]}s')
        if not item.get('auto_start', True):
            config.append('Auto-start: off')
        if config:
            refs['config_lbl'].config(text='  '.join(config))
            refs['config_frame'].pack(fill=tk.X, padx=12, pady=(0, 2))
        else:
            refs['config_frame'].pack_forget()

        rframe = refs['results_frame']
        rlbls = refs['results_lbls']
        for lbl in rlbls:
            lbl.destroy()
        rlbls.clear()
        if hist:
            results = hist[-1].get('results', [])
            if results:
                rframe.pack(fill=tk.X, padx=12, pady=(0, 2),
                            before=refs['stats_frame'])
                for r in results:
                    ok = r.endswith(': ok')
                    lbl = tk.Label(rframe, text=f'  {r}', font=('Consolas', 8),
                                   bg=self._s['bg'],
                                   fg=self._s['hint'] if ok else self._s['dead'],
                                   anchor='w')
                    lbl.pack(fill=tk.X)
                    rlbls.append(lbl)
            else:
                rframe.pack_forget()
        else:
            rframe.pack_forget()

    # ===================================================================
    #  form dialog
    # ===================================================================

    def _show_form(self, task_id=None):
        if self._form_win and self._form_win.winfo_exists():
            self._form_win.lift()
            self._form_win.focus_force()
            return

        editing = task_id is not None
        item = (self._srv('get', task_id) or {}) if editing else {}

        s = self._s
        l = self._l
        dlg = tk.Toplevel(self)
        dlg.withdraw()  # hide until fully built and positioned
        dlg.title(l['edit_task'] if editing else l['add_task_title'])
        dlg.resizable(True, True)
        dlg.configure(bg=s['bg'])
        dlg.transient(self)
        self._form_win = dlg
        dlg.protocol('WM_DELETE_WINDOW', lambda: (self._form_win.destroy(),
                                                    setattr(self, '_form_win', None)))
        self.app.emit('app@window:set-icon', dlg)

        P = {'padx': 10, 'pady': 3}

        # ---- task_id ----
        f = tk.Frame(dlg, bg=s['bg']); f.pack(fill=tk.X, **P)
        tk.Label(f, text=l['form_task_id'], font=('Consolas', 9), bg=s['bg'],
                 fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        id_var = tk.StringVar(value=task_id or '')
        e = tk.Entry(f, textvariable=id_var, font=('Consolas', 9),
                     bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                     relief=tk.FLAT)
        e.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ---- type ----
        f = tk.Frame(dlg, bg=s['bg']); f.pack(fill=tk.X, **P)
        tk.Label(f, text=l['form_type'], font=('Consolas', 9), bg=s['bg'],
                 fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        type_var = tk.StringVar(value=item.get('type', 'every'))
        for t in ('once', 'every', 'daily', 'weekly', 'cron'):
            tk.Radiobutton(f, text=t, variable=type_var, value=t,
                           font=('Consolas', 9), bg=s['bg'], fg=s['fg'],
                           selectcolor=s['card'],
                           activebackground=s['bg'], activeforeground=s['fg'],
                           command=lambda: _toggle_type()).pack(side=tk.LEFT, padx=4)

        # ---- type-specific params ----
        detail = tk.Frame(dlg, bg=s['bg'])
        detail.pack(fill=tk.X, padx=22, pady=(0, 4))

        # Placeholders: real definitions follow after UI widgets are created
        _toggle_type = lambda: None
        _update_cron_preview = lambda *_: None

        every_f = tk.Frame(detail, bg=s['bg'])
        tk.Label(every_f, text=l['form_interval'], font=('Consolas', 9),
                 bg=s['bg'], fg=s['hint'], anchor='w').pack(side=tk.LEFT)
        every_var = tk.StringVar(value=str(item.get('interval', '')))
        tk.Entry(every_f, textvariable=every_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT, width=8).pack(side=tk.LEFT, padx=4)

        once_f = tk.Frame(detail, bg=s['bg'])
        dly = str(item.get('delay', ''))
        once_mode = tk.StringVar(value='at' if ':' in dly else 'delay')
        tk.Radiobutton(once_f, text=l['form_delay'], variable=once_mode,
                       value='delay', font=('Consolas', 9), bg=s['bg'],
                       fg=s['fg'], selectcolor=s['card'],
                       activebackground=s['bg'], activeforeground=s['fg'],
                       command=lambda: _toggle_once()).pack(side=tk.LEFT, padx=2)
        tk.Radiobutton(once_f, text=l['form_at'], variable=once_mode,
                       value='at', font=('Consolas', 9), bg=s['bg'],
                       fg=s['fg'], selectcolor=s['card'],
                       activebackground=s['bg'], activeforeground=s['fg'],
                       command=lambda: _toggle_once()).pack(side=tk.LEFT, padx=2)

        once_delay_f = tk.Frame(once_f, bg=s['bg'])
        once_delay_var = tk.StringVar(value=dly if dly and ':' not in dly else '')
        tk.Entry(once_delay_f, textvariable=once_delay_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT, width=8).pack(side=tk.LEFT, padx=6)

        once_at_f = tk.Frame(once_f, bg=s['bg'])
        once_at_time = _make_time_picker(once_at_f, dly if ':' in dly else '')

        def _toggle_once():
            once_delay_f.pack_forget()
            once_at_f.pack_forget()
            if once_mode.get() == 'delay':
                once_delay_f.pack(side=tk.LEFT)
            else:
                once_at_f.pack(side=tk.LEFT)

        _toggle_once()

        def _get_once_value():
            if once_mode.get() == 'delay':
                return once_delay_var.get().strip()
            else:
                return once_at_time()

        daily_f = tk.Frame(detail, bg=s['bg'])
        tk.Label(daily_f, text=l['form_time'], font=('Consolas', 9),
                 bg=s['bg'], fg=s['hint'], anchor='w').pack(side=tk.LEFT)
        daily_time = _make_time_picker(daily_f, item.get('time_str', ''))

        weekly_f = tk.Frame(detail, bg=s['bg'])
        tk.Label(weekly_f, text=l['form_days'], font=('Consolas', 9),
                 bg=s['bg'], fg=s['hint'], anchor='w').pack(side=tk.LEFT)
        day_vars = {}
        saved_days = set(item.get('days') or [])
        for i, name in enumerate(_WEEKDAY_NAMES):
            day_vars[i] = tk.BooleanVar(value=i in saved_days)
            tk.Checkbutton(weekly_f, text=name, variable=day_vars[i],
                           font=('Consolas', 8), bg=s['bg'], fg=s['fg'],
                           selectcolor=s['card'],
                           activebackground=s['bg'],
                           activeforeground=s['fg']).pack(side=tk.LEFT, padx=2)
        tk.Label(weekly_f, text=f'  {l["form_time"]}', font=('Consolas', 9),
                 bg=s['bg'], fg=s['hint']).pack(side=tk.LEFT)
        weekly_time = _make_time_picker(weekly_f, item.get('time_str', ''))

        cron_f = tk.Frame(detail, bg=s['bg'])
        tk.Label(cron_f, text=l['form_cron'], font=('Consolas', 9),
                 bg=s['bg'], fg=s['hint'], anchor='w').pack(side=tk.LEFT)
        cron_var = tk.StringVar(value=item.get('cron_expr', ''))
        tk.Entry(cron_f, textvariable=cron_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT, width=22).pack(side=tk.LEFT, padx=4)

        cron_preview = tk.Label(cron_f, text='', font=('Consolas', 7),
                                 bg=s['bg'], fg=s['hint'])
        cron_preview.pack(side=tk.LEFT, padx=4)

        _type_frames = {'every': every_f, 'once': once_f,
                        'daily': daily_f, 'weekly': weekly_f, 'cron': cron_f}

        def _toggle_type():
            for f2 in _type_frames.values():
                f2.pack_forget()
            sel = type_var.get()
            _type_frames[sel].pack(fill=tk.X)
            if sel == 'once':
                max_runs_frame.pack_forget()
            else:
                max_runs_frame.pack(side=tk.LEFT, before=timeout_lbl)
            if sel == 'cron':
                _update_cron_preview()

        def _update_cron_preview(*_):
            expr = cron_var.get().strip()
            if expr:
                try:
                    runs = next_cron_runs(expr, 3)
                    cron_preview.config(text=l['form_next'] + ', '.join(runs))
                except Exception:
                    cron_preview.config(text=l['form_invalid'])
            else:
                cron_preview.config(text='')

        cron_var.trace_add('write', _update_cron_preview)

        # ---- target ----
        f = tk.Frame(dlg, bg=s['bg']); f.pack(fill=tk.X, **P)
        tk.Label(f, text=l['form_target'], font=('Consolas', 9), bg=s['bg'],
                 fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        fn_var = tk.StringVar(value=item.get('fn_ref', ''))
        tk.Entry(f, textvariable=fn_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(dlg, text=l['form_target_hint'], font=('Consolas', 7),
                 bg=s['bg'], fg=s['hint'], anchor='w', justify=tk.LEFT).pack(
            fill=tk.X, padx=22, pady=(1, 2))

        # ---- args (positional) ----
        f = tk.Frame(dlg, bg=s['bg']); f.pack(fill=tk.X, **P)
        tk.Label(f, text='Args', font=('Consolas', 9), bg=s['bg'],
                 fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        saved_args = item.get('args', ())
        args_var = tk.StringVar(value=', '.join(saved_args) if saved_args else '')
        tk.Entry(f, textvariable=args_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(dlg, text='  逗号分隔，如: hello, 42', font=('Consolas', 7),
                 bg=s['bg'], fg=s['hint'], anchor='w').pack(
            fill=tk.X, padx=22, pady=(0, 2))

        # ---- kwargs (keyword) ----
        f = tk.Frame(dlg, bg=s['bg']); f.pack(fill=tk.X, **P)
        tk.Label(f, text='Kwargs', font=('Consolas', 9), bg=s['bg'],
                 fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        add_kv_btn = tk.Label(f, text='＋', font=('Consolas', 10, 'bold'),
                               bg=s['bar'], fg=s['accent'], padx=8,
                               cursor='hand2')
        add_kv_btn.pack(side=tk.RIGHT)

        # ---- kv_frame placeholder (packed before options) ----
        kv_frame = tk.Frame(dlg, bg=s['bg'])
        kv_frame.pack(fill=tk.X)
        kv_rows = []  # list of (key_var, val_var, row_frame)
        saved_kwargs = item.get('kwargs', {})

        def _add_kv_row(key='', value=''):
            row = tk.Frame(kv_frame, bg=s['bg'])
            row.pack(fill=tk.X)
            key_var = tk.StringVar(value=key)
            val_var = tk.StringVar(value=value)
            tk.Entry(row, textvariable=key_var, font=('Consolas', 9),
                     bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                     relief=tk.FLAT, width=12).pack(side=tk.LEFT, padx=(0, 4))
            tk.Entry(row, textvariable=val_var, font=('Consolas', 9),
                     bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                     relief=tk.FLAT).pack(side=tk.LEFT, fill=tk.X, expand=True)
            del_btn = tk.Label(row, text='✕', font=('Consolas', 9),
                               bg=s['bg'], fg=s['dead'], padx=4, cursor='hand2')
            del_btn.pack(side=tk.RIGHT)
            del_btn.bind('<Button-1>', lambda e, r=row: _remove_kv_row(r))
            kv_rows.append((key_var, val_var, row))

        def _remove_kv_row(row):
            for i, (k, v, r) in enumerate(kv_rows):
                if r is row:
                    row.destroy()
                    kv_rows.pop(i)
                    break

        add_kv_btn.bind('<Button-1>', lambda e: _add_kv_row())

        if saved_kwargs:
            for k, v in saved_kwargs.items():
                _add_kv_row(k, v)

        # ---- options ----
        opt = tk.Frame(dlg, bg=s['bg']); opt.pack(fill=tk.X, **P)
        auto_var = tk.BooleanVar(value=item.get('auto_start', True))
        tk.Checkbutton(opt, text=l['form_auto_start'], variable=auto_var,
                       font=('Consolas', 9), bg=s['bg'], fg=s['fg'],
                       selectcolor=s['card'],
                       activebackground=s['bg'],
                       activeforeground=s['fg']).pack(side=tk.LEFT, padx=2)

        max_runs_frame = tk.Frame(opt, bg=s['bg'])
        max_runs_frame.pack(side=tk.LEFT)
        tk.Label(max_runs_frame, text=f'  {l["form_max_runs"]}', font=('Consolas', 9),
                 bg=s['bg'], fg=s['hint']).pack(side=tk.LEFT)
        max_var = tk.StringVar(value=str(item.get('max_runs', '') if item.get('max_runs') else ''))
        tk.Entry(max_runs_frame, textvariable=max_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT, width=5).pack(side=tk.LEFT, padx=2)

        timeout_lbl = tk.Label(opt, text='  Timeout(s)', font=('Consolas', 9),
                                bg=s['bg'], fg=s['hint'])
        timeout_lbl.pack(side=tk.LEFT, padx=(10, 2))
        timeout_var = tk.StringVar(value=str(item.get('timeout', '') if item.get('timeout') else ''))
        tk.Entry(opt, textvariable=timeout_var, font=('Consolas', 9),
                 bg=s['card'], fg=s['fg'], insertbackground=s['fg'],
                 relief=tk.FLAT, width=5).pack(side=tk.LEFT, padx=2)

        # ---- buttons ----
        bf = tk.Frame(dlg, bg=s['bg'])
        bf.pack(fill=tk.X, padx=10, pady=(8, 10))
        err_var = tk.StringVar(value='')
        tk.Label(bf, textvariable=err_var, font=('Consolas', 8, 'bold'),
                 bg=s['bg'], fg=s['dead'], anchor='w').pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        tk.Button(bf, text=l['form_cancel'], command=dlg.destroy,
                  bg=s['bar'], fg=s['fg'], relief=tk.FLAT, padx=12,
                  font=('Consolas', 9)).pack(side=tk.RIGHT, padx=4)
        tk.Button(bf, text=l['form_save'], command=lambda: _save(),
                  bg=s['accent'], fg=s['accent_fg'], relief=tk.FLAT, padx=16,
                  font=('Consolas', 9, 'bold'), activebackground='#3a6fa8',
                  activeforeground='#fff').pack(side=tk.RIGHT, padx=4)

        def _save():
            nonlocal editing
            err_var.set('')
            tid = id_var.get().strip()
            tp = type_var.get()
            fn = fn_var.get().strip()

            if not tid:
                err_var.set(l['form_validate_id']); return
            if not fn:
                err_var.set(l['form_validate_target']); return

            mr_str = max_var.get().strip()
            mr = 0
            if mr_str:
                try:
                    mr = int(mr_str)
                except ValueError:
                    err_var.set(l['form_validate_number']); return

            to_str = timeout_var.get().strip()
            to = 0
            if to_str:
                try:
                    to = int(to_str)
                except ValueError:
                    err_var.set(l['form_validate_number']); return

            au = auto_var.get()

            # ---- args & kwargs ----
            args_str = args_var.get().strip()
            task_args = tuple(a.strip() for a in args_str.split(',') if a.strip()) if args_str else ()
            task_kwargs = {}
            for k, v, r in kv_rows:
                key = k.get().strip()
                if key:
                    task_kwargs[key] = v.get().strip()

            try:
                if not editing and tid in self._all_tasks():
                    err_var.set(l['form_validate_dup']); return
                if editing and tid != task_id and tid in self._all_tasks():
                    err_var.set(l['form_validate_dup']); return
                if editing and tid != task_id:
                    self._srv('cancel', task_id)
                    editing = False

                result = None
                if tp == 'every':
                    val = every_var.get().strip()
                    if not val:
                        err_var.set(l['form_validate_interval']); return
                    fv = float(val)
                    if fv <= 0:
                        err_var.set(l['form_validate_interval']); return
                    result = self._srv('create_every', tid, fv, fn,
                              auto_start=au, max_runs=mr, timeout=to,
                              updating=editing, args=task_args, kwargs=task_kwargs)
                elif tp == 'once':
                    val = _get_once_value()
                    if not val:
                        err_var.set(l['form_validate_delay']); return
                    result = self._srv('create_once', tid, val, fn,
                              auto_start=au, timeout=to, updating=editing,
                              args=task_args, kwargs=task_kwargs)
                elif tp == 'daily':
                    result = self._srv('create_daily', tid, daily_time(), fn,
                              auto_start=au, max_runs=mr, timeout=to,
                              updating=editing, args=task_args, kwargs=task_kwargs)
                elif tp == 'weekly':
                    days = [i for i, v in day_vars.items() if v.get()]
                    if not days:
                        err_var.set(l['form_validate_days']); return
                    result = self._srv('create_weekly', tid, days, weekly_time(), fn,
                              auto_start=au, max_runs=mr, timeout=to,
                              updating=editing, args=task_args, kwargs=task_kwargs)
                elif tp == 'cron':
                    expr = cron_var.get().strip()
                    if expr and not validate_cron(expr):
                        err_var.set(l['form_validate_cron']); return
                    result = self._srv('create_cron', tid, expr, fn,
                              auto_start=au, max_runs=mr, timeout=to,
                              updating=editing, args=task_args, kwargs=task_kwargs)
                if result is None:
                    err_var.set('Service unavailable')
                    return
                self._form_win = None
                dlg.destroy()
                self._rebuild_ui()
            except (ValueError, KeyError) as exc:
                err_var.set(str(exc)[:60])

        _toggle_type()
        dlg.geometry('+%d+%d' % (self.winfo_rootx() + 40, self.winfo_rooty() + 40))
        dlg.deiconify()
        dlg.focus_set()

    # ===================================================================
    #  help
    # ===================================================================

    def _show_help(self):
        if self._help_win and self._help_win.winfo_exists():
            self._help_win.lift()
            self._help_win.focus_force()
            return
        self._help_win = PluginGuide(self, self.app, doc='task-scheduler.md',
                                     title_zh='任务调度器 帮助',
                                     title_en='Task Scheduler Help')
        self.app.emit('app@window:set-icon', self._help_win)

    def on_destroy(self):
        pass
