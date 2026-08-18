# -*- coding: utf-8 -*-
"""Task Scheduler panel — GuiPlugin, pure UI management.

Requires TasksService (task_service.py) to be running at the app level.
Communicates via services: tasks@list, tasks@get, tasks@create_*, etc.
"""
import json
import time
import tkinter as tk
from tkinter import filedialog

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

ENTRY_IPADY = 2

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

_LANG = {
    'zh': {
        'title':           '任务调度器',
        'no_tasks':        '暂无任务',
        'add_task':        '+ 新建',
        'import_tasks':    '导入',
        'export_tasks':    '导出',
        'pause_all':       '全部暂停',
        'resume_all':      '全部恢复',
        'status_failed':   '失败',
        'col_id':          'ID',
        'col_type':        '类型',
        'col_last':        '上次执行',
        'col_operator':    '操作',
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
        'form_start_time': '起始时间',
        'form_start_time_hint': '可选，计时锚点 (HH:MM:SS / 时间戳 / 日期时间)',
        'form_delay':      '延迟/时间',
        'form_delay_hint': '相对秒数 / HH:MM:SS / 日期时间(如 2026-08-05 14:30:00)',
        'form_time':       '时间',
        'form_days':       '星期',
        'form_cron':       'Cron 表达式',
        'form_target_hint': '格式: 命名空间@方法名\n多个用逗号分隔, 例如: notify@banner, notify@popup',
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
        'import_tasks':    'Import',
        'export_tasks':    'Export',
        'pause_all':       'Pause All',
        'resume_all':      'Resume All',
        'status_failed':   'failed',
        'col_id':          'ID',
        'col_type':        'Type',
        'col_last':        'Last Run',
        'col_operator':    'Operator',
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
        'form_start_time': 'Start Time',
        'form_start_time_hint': 'Optional anchor (HH:MM:SS / timestamp / datetime)',
        'form_delay':      'Delay',
        'form_delay_hint': 'relative secs / HH:MM:SS / datetime (e.g. 2026-08-05 14:30:00)',
        'form_time':       'Time',
        'form_days':       'Days',
        'form_cron':       'Cron',
        'form_target_hint': 'Format: namespace@method\nComma-separated for multiple, e.g: notify@banner, notify@popup',
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
# helpers
# ---------------------------------------------------------------------------

def _make_time_picker(parent, initial='', components=None, theme=None):
    """Build an HH:MM:SS picker.

    *components* = app 组件库 (主题感知), *theme* = 当前主题字典.
    """
    comp = components if components is not None else tk
    hint = theme.get('hint', '#888') if theme else '#888'
    f = comp.Frame(parent)
    parts = initial.split(':') if initial else ['', '']
    h = parts[0] if len(parts) > 0 and parts[0].isdigit() else '00'
    m = parts[1] if len(parts) > 1 and parts[1].isdigit() else '00'
    sec = parts[2] if len(parts) > 2 and parts[2].isdigit() else '00'
    hours = [f'{i:02d}' for i in range(24)]
    mins = [f'{i:02d}' for i in range(60)]
    secs = [f'{i:02d}' for i in range(60)]
    h_var = tk.StringVar(value=h)
    comp.Combobox(f, textvariable=h_var, values=hours,
                  font=comp.mono_font(9), width=3, state='readonly').pack(side=tk.LEFT, ipady=ENTRY_IPADY)
    comp.Label(f, text=':', font=comp.mono_font(9),
               fg=hint).pack(side=tk.LEFT)
    m_var = tk.StringVar(value=m)
    comp.Combobox(f, textvariable=m_var, values=mins,
                  font=comp.mono_font(9), width=3, state='readonly').pack(side=tk.LEFT, ipady=ENTRY_IPADY)
    comp.Label(f, text=':', font=comp.mono_font(9),
               fg=hint).pack(side=tk.LEFT)
    s_var = tk.StringVar(value=sec)
    comp.Combobox(f, textvariable=s_var, values=secs,
                  font=comp.mono_font(9), width=3, state='readonly').pack(side=tk.LEFT, ipady=ENTRY_IPADY)
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
    priority = 995
    reload = True
    fixed_position = True
    fixed_size = False

    _GROUP_ORDER = ('active', 'failed', 'off', 'done')

    def __init__(self, parent=None, app=None):
        super().__init__(parent, app)

        lang_name = self.app.current_lang_name
        self._l = _LANG.get(lang_name, _LANG['en'])
        self._s = self.app.theme
        s = self._s
        l = self._l

        self.title(l['title'])
        self.resizable(True, True)
        self.minsize(666, 520)

        self._rows = {}
        self._expanded = set()
        self._detail_frames = {}
        self._group_labels = {}  # group_key -> Label widget
        self._group_seps = {}    # 'sep_{key}' -> separator Frame
        self._row_cache = {}     # tid -> {display-relevant fields for diff}
        self._help_win = None
        self._form_win = None

        # ---- toolbar ----
        bar = self.components.Frame(self, bg=s['bar'], height=32)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        self._status_lbl = self.components.Label(bar, text='',
                                                 font=self.components.mono_font(8),
                                                 bg=s['bar'], fg=s['hint'])
        self._status_lbl.pack(side=tk.LEFT, padx=10, pady=4)

        self._pause_btn = self.components.Button(
            bar, text=l['pause_all'], font=self.components.mono_font(10))
        self._pause_btn.bind('<Button-1>', lambda e: self._toggle_global_pause())
        # 右 8 与下方内容区右缘对齐
        self._pause_btn.pack(side=tk.RIGHT, padx=(2, 8), pady=4)

        for text, cmd in [
            (l['import_tasks'], self._import_tasks),
            (l['export_tasks'], self._export_tasks),
            (l['add_task'], self._show_form),
            ('?', self._show_help),
        ]:
            lbl = self.components.Button(
                bar, text=text,
                font=self.components.mono_font(10))
            lbl.bind('<Button-1>', lambda e, c=cmd: c())
            lbl.pack(side=tk.RIGHT, padx=2, pady=4)

        # ---- table header ----
        hdr = self.components.Frame(self, bg=s['bar'])
        hdr.pack(fill=tk.X, side=tk.TOP, padx=8, pady=(8, 0))
        hdr_lbls = [l['col_id'], l['col_type'], l['col_last'], l['col_operator']]
        hdr_widths = (40, 10, None, 12)
        for label, w in zip(hdr_lbls, hdr_widths):
            kw = {'width': w} if w else {}
            lbl = self.components.Label(hdr, text=label,
                                        font=self.components.mono_font(10, 'bold'),
                                        bg=s['bar'], fg=s['hint'], anchor='w',
                                        **kw)
            lbl.pack(side=tk.LEFT, padx=1,
                     fill=tk.X if w is None else tk.NONE,
                     expand=w is None)
            if label == l['col_operator']:
                self._hdr_ops_lbl = lbl
        # 滚动条区域占位（与行内操作区右缘对齐）
        self.components.Frame(hdr, bg=s['bar'], width=12).pack(
            side=tk.RIGHT, fill=tk.Y)

        self.components.Frame(self, bg=s['hint'], height=1).pack(fill=tk.X, padx=8)

        # ---- scrollable content ----
        scroll_frame = self.components.Frame(self)
        # 底部 5 + 行 pady 1 = 6，与日志窗口按钮距底边框一致
        scroll_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 5))

        self._canvas = self.components.ScrollableCanvas(scroll_frame)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inner = self._canvas.inner

        self._empty = self.components.Label(self._inner, text=l['no_tasks'],
                                            font=self.components.mono_font(10),
                                            fg=s['hint'])
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
            self._sync_display()
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

    @staticmethod
    def _is_failed(task):
        """True if *task* is dead, explicitly failed, or heuristically failed."""
        if task.get('dead') or task.get('failed'):
            return True
        # Heuristic: errors>0 + disabled → likely failed (flag lost on restart)
        return task.get('errors', 0) > 0 and not task.get('enabled', True)

    def _status_text(self, task):
        if task.get('dead'):
            return self._l['status_dead']
        if self._is_failed(task):
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
        if self._is_failed(task):
            return 'failed'
        if self._is_done(task):
            return 'done'
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
        return '─' * 30 + f' {labels.get(key, key)} ({count}) ' + '─' * 30

    def _rebuild_ui(self):
        for w in self._inner.winfo_children():
            if w is not self._empty:
                w.destroy()
        self._rows.clear()
        self._detail_frames.clear()
        self._group_labels.clear()
        self._group_seps.clear()
        self._row_cache.clear()
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
                sep = self.components.Frame(self._inner, bg=s['hint'], height=1)
                sep.pack(fill=tk.X, padx=0, pady=(6, 2))
                self._group_seps[f'_sep_{key}'] = sep
            first = False
            glbl = self.components.Label(self._inner,
                                        text=self._group_title(key, len(items)),
                                        font=self.components.mono_font(9, 'bold'),
                                        fg=s['hint'], anchor='w')
            glbl.pack(fill=tk.X, padx=0, pady=(2, 1))
            self._group_labels[key] = glbl

            for tid, task in sorted(items, key=lambda x: x[0]):
                self._add_row(tid, task, s)

    def _ensure_groups(self):
        """Pre-create group labels and separators (once, reused forever)."""
        s = self._s
        for key in self._GROUP_ORDER:
            if key not in self._group_labels:
                glbl = self.components.Label(self._inner,
                                             font=self.components.mono_font(9, 'bold'),
                                             fg=s['hint'], anchor='w')
                self._group_labels[key] = glbl
            sep_key = f'_sep_{key}'
            if sep_key not in self._group_seps:
                self._group_seps[sep_key] = self.components.Frame(
                    self._inner, bg=s['hint'], height=1)

    def _update_all_group_labels(self):
        """Refresh group label counts and hide empty groups."""
        for key in self._GROUP_ORDER:
            all_tids = [t for t, rd in self._rows.items() if rd['group'] == key]
            if key in self._group_labels:
                if all_tids:
                    self._group_labels[key].config(
                        text=self._group_title(key, len(all_tids)))
                else:
                    self._group_labels[key].pack_forget()
                    sep = self._group_seps.get(f'_sep_{key}')
                    if sep:
                        sep.pack_forget()

    def _insert_new_rows(self, added):
        """Insert newly created rows, then repack everything in group order.

        Rows are already created with pack=False; a full repack places each
        row and its group header at the correct sorted position.  (Incremental
        after= placement proved unreliable when several rows relocate at once:
        a row could be packed after another row that had not relocated yet,
        leaving it stranded outside its group.)
        """
        self._ensure_groups()
        self._repack_rows()

    def _relocate_row(self, tid):
        """Move an existing row to its correct position (after group change).

        Row's ``group`` is already updated by the caller; a full repack
        places it (and any other rows in the same pass) at the correct
        sorted position.  See ``_insert_new_rows`` for why incremental
        after= placement was abandoned.
        """
        self._ensure_groups()
        self._repack_rows()

    def _repack_rows(self):
        """Repack rows, details, separators, labels without destroying widgets."""
        s = self._s
        for w in self._inner.winfo_children():
            if w is not self._empty:
                w.pack_forget()

        grouped = {k: [] for k in self._GROUP_ORDER}
        for tid, row_data in self._rows.items():
            grouped[row_data['group']].append(tid)

        first = True
        for key in self._GROUP_ORDER:
            items = grouped.get(key, [])
            if not items:
                continue
            if not first:
                self._group_seps[f'_sep_{key}'].pack(
                    fill=tk.X, padx=0, pady=(6, 2))
            first = False

            self._group_labels[key].config(
                text=self._group_title(key, len(items)))
            self._group_labels[key].pack(fill=tk.X, padx=(0, 8), pady=(2, 1))

            for tid in sorted(items):
                self._rows[tid]['row'].pack(fill=tk.X, padx=(0, 8), pady=1)
                detail = self._detail_frames.get(tid)
                if detail:
                    detail['frame'].pack(fill=tk.X, padx=(0, 8), pady=(0, 2))

        if any(grouped.values()):
            self._empty.pack_forget()
        else:
            self._empty.pack(pady=30)

    def _add_row(self, tid, task, s, pack=True):
        disabled = not task.get('enabled', True)
        is_done = self._is_done(task)

        row = self.components.Card(self._inner)
        if pack:
            row.pack(fill=tk.X, padx=(0, 8), pady=1)

        if self._is_failed(task):
            fg = s['danger']
        elif disabled or is_done:
            fg = s['hint']
        elif task.get('firing'):
            fg = s['accent']
        else:
            fg = s['fg']

        # last_fired = 真实执行时间 (last_run 兼作调度锚点, 重启时会被重置)
        last_str = '-' if not task.get('last_fired') else \
                   time.strftime('%m-%d %H:%M:%S', time.localtime(task['last_fired']))
        # vals = [tid, task['type'], last_str, self._status_text(task)]
        vals = [tid, task['type'], last_str]

        row.bind('<Button-1>', lambda e, t=tid: self._toggle_expand(t))
        lbls = []
        widths = (40, 10, None, 10)
        for v, w in zip(vals, widths):
            kw = {'width': w} if w else {}
            lbl = self.components.Label(row, text=str(v)[:30],
                                        font=self.components.mono_font(10),
                                        bg=s['card'], fg=fg, anchor='w', **kw)
            lbl.pack(side=tk.LEFT, padx=1, fill=tk.X if w is None else tk.NONE,
                     expand=w is None)
            lbl.bind('<Button-1>', lambda e, t=tid: self._toggle_expand(t))
            lbls.append(lbl)

        # 操作区：与表头"操作"列同宽同位置（左缘右缘完全对齐）；
        # 背景与按钮同色（card），按钮连成一块无视觉缝隙。
        # 按钮从左排：× 删除、⏸ 暂停、✎ 编辑
        ops = self.components.Frame(row, bg=s['card'],
                                    width=self._hdr_ops_lbl.winfo_reqwidth())
        ops.pack(side=tk.RIGHT, fill=tk.Y)
        ops.pack_propagate(False)

        # cancel（先 pack → 最左）
        self.components.Button(
            ops, text='×', command=lambda t=tid: self._do_cancel(t),
            font=self.components.mono_font(10), width=2, padx=4,
            bg=s['card'], fg=s['danger']).pack(side=tk.LEFT, padx=3)

        # pause / play
        if is_done:
            pause_text = '✓'
            pause_fg = s['hint']
        elif disabled or self._is_failed(task):
            pause_text = '▶'
            pause_fg = s['hint']
        else:
            pause_text = '⏸'
            pause_fg = s['fg']
        pause_btn = self.components.Button(
            ops, text=pause_text, font=self.components.mono_font(10),
            bg=s['card'], fg=pause_fg, width=2, padx=4,
            command=lambda t=tid: self._do_toggle(t))
        # pause_btn.bind('<Button-1>',
        #                lambda e, t=tid: self._do_toggle(t))
        pause_btn.pack(side=tk.LEFT, padx=3)

        # edit（最后 pack → 最右）
        def _edit_cmd(t=tid):
            self._show_form(t)
        self.components.Button(
            ops, text='✎', command=_edit_cmd,
            font=self.components.mono_font(10),
            bg=s['card'], width=2, padx=4).pack(side=tk.LEFT, padx=3)

        self._rows[tid] = {'labels': lbls, 'pause_btn': pause_btn,
                           'row': row, 'fg': fg, 'group': self._task_group(task)}

    # ------------------------------------------------------------------
    #  row-level incremental updates
    # ------------------------------------------------------------------

    _CACHE_KEYS = ('dead', 'failed', 'enabled', 'firing', 'last_run',
                   'last_fired', 'count', 'errors')

    def _row_needs_update(self, tid, task):
        """Return True if *task* display differs from cached row state."""
        cache = self._row_cache.get(tid)
        if not cache:
            return True
        for k in self._CACHE_KEYS:
            if cache.get(k) != task.get(k):
                return True
        if self._is_done(task) != cache.get('_done', False):
            return True
        return False

    def _update_row(self, tid, task):
        """Update an existing row's labels and buttons in-place."""
        s = self._s
        row_data = self._rows.get(tid)
        if not row_data:
            return

        disabled = not task.get('enabled', True)
        is_done = self._is_done(task)

        if self._is_failed(task):
            fg = s['danger']
        elif disabled or is_done:
            fg = s['hint']
        elif task.get('firing'):
            fg = s['accent']
        else:
            fg = s['fg']

        last_str = '-' if not task.get('last_fired') else \
                   time.strftime('%m-%d %H:%M:%S', time.localtime(task['last_fired']))
        vals = [tid, task['type'], last_str, self._status_text(task)]
        for lbl, v in zip(row_data['labels'], vals):
            lbl.config(text=str(v)[:30], fg=fg)
        row_data['fg'] = fg

        # pause / play button
        pause_btn = row_data.get('pause_btn')
        if pause_btn and not is_done:
            if disabled or self._is_failed(task):
                pause_btn.config(text='▶', fg=s['hint'])
            else:
                pause_btn.config(text='⏸', fg=s['fg'])
        elif pause_btn:
            pause_btn.config(text='✓', fg=s['hint'])

        # Update expanded detail
        if tid in self._expanded:
            self._refresh_detail(tid)

        # Update cache
        self._row_cache[tid] = {k: task.get(k) for k in self._CACHE_KEYS}
        self._row_cache[tid]['_done'] = is_done

    def _remove_row(self, tid):
        """Destroy a single row and its detail frame."""
        row_data = self._rows.pop(tid, None)
        if row_data:
            row_data['row'].destroy()
        detail = self._detail_frames.pop(tid, None)
        if detail:
            detail['frame'].destroy()
        self._expanded.discard(tid)
        self._row_cache.pop(tid, None)

    def _do_toggle(self, tid):
        item = self._srv('get', tid)
        if not item or tid not in self._rows:
            return

        # 完成的任务: 点击 = 重新执行 (一次点击生效; once 可能 fired 但
        # enabled=True — 旧逻辑第一次只 pause, UI 无变化)
        if self._is_done(item):
            self._srv('restart', tid)
            item = self._srv('get', tid)
            if not item or tid not in self._rows:
                return
            old_group = self._rows[tid]['group']
            new_group = self._task_group(item)
            self._rows[tid]['group'] = new_group
            self._update_row(tid, item)
            if old_group != new_group:
                self._relocate_row(tid)
            return

        was_enabled = item.get('enabled', True)
        if was_enabled:
            self._srv('pause', tid)
            item = dict(item)
            item['enabled'] = False
        elif item['type'] == 'once':
            # once + numeric delay → cancel & recreate to reset countdown
            delay = item.get('delay', '')
            try:
                float(delay)
                # numeric delay: recreate so timer starts from now
                extra = {k: item[k] for k in self._IMPORT_EXTRA['once']
                         if k in item}
                self._srv('cancel', tid)
                self._srv('create_once', tid, delay, item['fn_ref'],
                          updating=False, **extra)
                item = self._srv('get', tid)
                if not item:
                    return
            except (ValueError, TypeError):
                # absolute time: just resume
                self._srv('resume', tid)
                item = self._srv('get', tid)
                if not item:
                    return
        else:
            self._srv('resume', tid)
            item = self._srv('get', tid)
            if not item:
                return
        old_group = self._rows[tid]['group']
        new_group = self._task_group(item)
        self._rows[tid]['group'] = new_group
        self._update_row(tid, item)
        if old_group != new_group:
            self._relocate_row(tid)

    def _do_cancel(self, tid):
        self._srv('cancel', tid)
        self._remove_row(tid)
        self._update_all_group_labels()

    def _toggle_global_pause(self):
        if self._pause_btn.cget('text') == self._l['pause_all']:
            for t in self._all_tasks().values():
                if t.get('enabled'):
                    self._srv('pause', t['id'])
        else:
            for t in self._all_tasks().values():
                if not t.get('enabled') and not self._is_failed(t):
                    self._srv('resume', t['id'])
        self._sync_display()  # 按钮文本由 _sync_pause_btn 统一同步

    # ===================================================================
    #  import / export
    # ===================================================================

    _COMMON_KEYS = ('id', 'type', 'fn_ref', 'auto_start', 'enabled',
                    'max_runs', 'timeout', 'args', 'kwargs', 'created_at')
    _EXPORT_KEYS = {
        'every':  _COMMON_KEYS + ('interval', 'start_time'),
        'once':   _COMMON_KEYS + ('delay',),
        'daily':  _COMMON_KEYS + ('time_str',),
        'weekly': _COMMON_KEYS + ('days', 'time_str'),
        'cron':   _COMMON_KEYS + ('cron_expr',),
    }
    # Per-type whitelist of extra kwargs accepted on import (future-proof:
    # unknown keys in imported JSON are silently ignored).
    _IMPORT_EXTRA = {
        'every':  ('auto_start', 'max_runs', 'timeout', 'args', 'kwargs', 'start_time'),
        'once':   ('auto_start', 'timeout', 'args', 'kwargs'),
        'daily':  ('auto_start', 'max_runs', 'timeout', 'args', 'kwargs'),
        'weekly': ('auto_start', 'max_runs', 'timeout', 'args', 'kwargs'),
        'cron':   ('auto_start', 'max_runs', 'timeout', 'args', 'kwargs'),
    }
    # Fields whose zero value means "not set" (skip on export)
    _ZERO_IS_UNSET = frozenset({'max_runs', 'timeout'})

    def _export_tasks(self):
        tasks = self._all_tasks()
        if not tasks:
            self.components.showinfo(self._l['export_tasks'],
                                     self._l['no_tasks'], parent=self)
            return

        dlg = self.components.Toplevel(self)
        dlg.title(self._l['export_tasks'])
        dlg.transient(self)
        dlg.resizable(False, True)
        dlg.minsize(280, 200)
        dlg.geometry('+{}+{}'.format(self.winfo_rootx() + 60,
                                      self.winfo_rooty() + 60))

        def _do_export():
            export_list = []
            for tid, var in check_vars.items():
                if var.get() and tid in tasks:
                    t = tasks[tid]
                    keys = self._EXPORT_KEYS.get(t['type'], self._COMMON_KEYS)
                    item = {}
                    for k in keys:
                        v = t.get(k)
                        if v is None or v == '' or v == [] or v == {}:
                            continue
                        if k in self._ZERO_IS_UNSET and v == 0:
                            continue
                        if isinstance(v, (list, tuple)) and len(v) == 0:
                            continue
                        item[k] = v
                    # once + numeric delay → relative time, disable on import
                    if t['type'] == 'once':
                        try:
                            float(t.get('delay', ''))
                            item['enabled'] = False
                        except (ValueError, TypeError):
                            pass  # absolute time string, keep original
                    export_list.append(item)
            if not export_list:
                return
            path = filedialog.asksaveasfilename(
                parent=dlg, defaultextension='.json',
                filetypes=[('JSON', '*.json')])
            if path:
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        json.dump({'tasks': export_list,
                                   'exported_at': time.strftime('%Y-%m-%d %H:%M:%S')},
                                  f, ensure_ascii=False, indent=2)
                    dlg.destroy()
                except Exception as e:
                    self.components.showerror('Error', str(e), parent=self)

        # top bar: select-all + save button
        top_bar = self.components.Frame(dlg)
        top_bar.pack(fill=tk.X, padx=10, pady=(8, 4))
        select_all_var = tk.BooleanVar(value=True)
        cb_all = self.components.Checkbutton(
            top_bar, text='全选', variable=select_all_var,
            font=self.components.mono_font(10), selectcolor=self._s['card'])
        cb_all.pack(side=tk.LEFT)
        self.components.Button(
            top_bar, text='保存', command=_do_export,
            font=self.components.mono_font(9, 'bold')).pack(side=tk.RIGHT, padx=4)

        # scrollable checkbox area
        canvas = self.components.ScrollableCanvas(dlg)
        inner = canvas.inner
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))

        # task checkboxes inside scrollable area
        check_vars = {}
        for tid, t in sorted(tasks.items()):
            var = tk.BooleanVar(value=True)
            check_vars[tid] = var
            cb = self.components.Checkbutton(
                inner, text=f'{tid}  ({t["type"]})',
                variable=var, font=self.components.mono_font(9),
                selectcolor=self._s['card'])
            cb.pack(anchor='w', padx=0, pady=1)

        def _toggle_all():
            v = select_all_var.get()
            for var in check_vars.values():
                var.set(v)

        cb_all.config(command=_toggle_all)

    def _import_tasks(self):
        path = filedialog.askopenfilename(
            parent=self, filetypes=[('JSON', '*.json')])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.components.showerror('Error', str(e), parent=self)
            return

        items = data.get('tasks', data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return

        existing = self._all_tasks()
        added = 0
        skipped = 0
        for item in items:
            if not isinstance(item, dict) or 'id' not in item:
                continue
            tid = item['id']
            if tid in existing:
                skipped += 1
                continue
            tp = item.get('type', 'every')
            fn = item.get('fn_ref', '')
            if not fn:
                continue
            # once tasks: disable if delay is relative (numeric) or absolute
            # time already in the past (would fire immediately otherwise).
            if tp == 'once':
                delay = str(item.get('delay', ''))
                try:
                    float(delay)
                    item['enabled'] = False  # numeric → relative
                except ValueError:
                    parsed = False
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%H:%M:%S'):
                        try:
                            t = time.strptime(delay, fmt)
                            if fmt == '%H:%M:%S':
                                now = time.localtime()
                                t = time.struct_time((
                                    now.tm_year, now.tm_mon, now.tm_mday,
                                    t.tm_hour, t.tm_min, t.tm_sec,
                                    0, 0, now.tm_isdst))
                            if time.mktime(t) <= time.time():
                                item['enabled'] = False
                            parsed = True
                            break
                        except (ValueError, OverflowError):
                            continue
                    if not parsed:
                        item['enabled'] = False  # unrecognized format, disable
            # Only pass type-appropriate extra kwargs (future-proof: unknown
            # keys in imported JSON are silently ignored).
            extra = {k: item[k]
                     for k in self._IMPORT_EXTRA.get(tp, ())
                     if k in item}
            try:
                if tp == 'every':
                    self._srv('create_every', tid, item.get('interval', 60), fn,
                              updating=False, **extra)
                elif tp == 'once':
                    self._srv('create_once', tid, item.get('delay', ''), fn,
                              updating=False, **extra)
                elif tp == 'daily':
                    self._srv('create_daily', tid, item.get('time_str', '00:00'), fn,
                              updating=False, **extra)
                elif tp == 'weekly':
                    self._srv('create_weekly', tid, item.get('days', []),
                              item.get('time_str', '00:00'), fn,
                              updating=False, **extra)
                elif tp == 'cron':
                    self._srv('create_cron', tid, item.get('cron_expr', '* * * * *'), fn,
                              updating=False, **extra)
                else:
                    skipped += 1
                    continue
                added += 1
                # restore paused state
                if not item.get('enabled', True):
                    self._srv('pause', tid)
            except ValueError:
                skipped += 1  # duplicate ID
            except Exception as e:
                skipped += 1
                import traceback
                traceback.print_exc()

        self._sync_display(rebuild=True)
        self.components.showinfo(
            self._l['import_tasks'],
            f'导入 {added} 个任务，跳过 {skipped} 个', parent=self)

    def _sync_display(self, rebuild=False):
        """Incrementally sync the display with the current task list.

        - *rebuild*=True: destroy everything and recreate (import, cancel-all).
        - *rebuild*=False: create/update/remove rows one-by-one.
        """
        if rebuild:
            self._rebuild_ui()
            self._sync_pause_btn()
            return

        tasks = self._all_tasks()
        current_tids = set(tasks.keys())
        existing_tids = set(self._rows.keys())

        # 1. Remove rows for deleted tasks (just destroy, no repack needed)
        removed = existing_tids - current_tids
        for tid in removed:
            self._remove_row(tid)

        # 2. Create rows for new tasks
        added = current_tids - existing_tids
        for tid in added:
            self._add_row(tid, tasks[tid], self._s, pack=False)

        # 3. Detect group changes + diff rows in single pass
        changed_groups = []  # (tid,) tuples for relocate
        for tid, task in tasks.items():
            row_data = self._rows.get(tid)
            if not row_data or tid in added:
                continue
            new_group = self._task_group(task)
            if row_data['group'] != new_group:
                row_data['group'] = new_group
                changed_groups.append(tid)
            if self._row_needs_update(tid, task):
                self._update_row(tid, task)

        # 4. Apply changes: insert new rows, relocate moved rows, update labels
        if added:
            self._insert_new_rows(added)
        for tid in changed_groups:
            self._relocate_row(tid)
        if removed:
            # Update group labels after removals
            self._update_all_group_labels()

        # 5. Show/hide empty
        if tasks:
            self._empty.pack_forget()
        else:
            self._empty.pack(pady=30)

        # 6. Sync pause-all / resume-all button text
        self._sync_pause_btn(tasks)

    def _sync_pause_btn(self, tasks=None):
        """按任务状态刷新 全部暂停/全部恢复 按钮文本。

        存在可恢复(非 enabled 且未 failed)任务 → 全部恢复; 否则全部暂停。
        failed 任务(含启发式)不参与批量恢复。手动暂停/恢复单个任务后由
        tick 或下一次 _sync_display 兜底同步。
        """
        if tasks is None:
            tasks = self._all_tasks()
        has_resumable = any(
            not t.get('enabled') and not self._is_failed(t)
            for t in tasks.values())
        self._pause_btn.config(
            text=self._l['resume_all'] if has_resumable
            else self._l['pause_all'])

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
        df = self.components.Card(self._inner)
        df.pack(fill=tk.X, padx=(0, 8), pady=(0, 2), after=row)

        # line 1: Target header + created
        header = self.components.Frame(df)
        header.pack(fill=tk.X, padx=12, pady=(4, 0))
        target_lbl = self.components.Label(header, text='Target:',
                                           font=self.components.mono_font(8, 'bold'),
                                           anchor='w')
        target_lbl.pack(side=tk.LEFT)
        created_lbl = self.components.Label(header, font=self.components.mono_font(8),
                                            fg=s['hint'], anchor='w')
        created_lbl.pack(side=tk.RIGHT)

        # line 2: per-target services (always shown)
        targets_frame = self.components.Frame(df)
        targets_lbls = []

        # line 3: per-target results (only after execution)
        results_frame = self.components.Frame(df)
        results_lbls = []

        # line 3: stats
        stats_frame = self.components.Frame(df)
        stats_lbl = self.components.Label(stats_frame, font=self.components.mono_font(8),
                                          fg=s['hint'], anchor='w')
        stats_lbl.pack(side=tk.LEFT)

        # line 4: config
        config_frame = self.components.Frame(df)
        config_lbl = self.components.Label(config_frame, font=self.components.mono_font(8),
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
                    lbl = self.components.Label(tframe, text=f'  {t}',
                                                font=self.components.mono_font(8),
                                                fg=self._s['hint'], anchor='w')
                    lbl.pack(fill=tk.X)
                    tlbls.append(lbl)
            else:
                tframe.pack_forget()
        else:
            tframe.pack_forget()

        last = time.strftime('%Y-%m-%d %H:%M:%S',
                             time.localtime(item['last_fired'])) \
               if item['last_fired'] else '-'
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
            st = item.get('start_time')
            if st:
                stats.append(f'Start: {time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st))}')
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
                    lbl = self.components.Label(rframe, text=f'  {r}',
                                                font=self.components.mono_font(8),
                                                fg=self._s['hint'] if ok
                                                else self._s['danger'],
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
        dlg = self.components.Toplevel(self)
        dlg.title(l['edit_task'] if editing else l['add_task_title'])
        dlg.resizable(False, True)
        dlg.transient(self)
        self._form_win = dlg
        dlg.protocol('WM_DELETE_WINDOW', lambda: (self._form_win.destroy(),
                                                    setattr(self, '_form_win', None)))

        P = {'padx': 10, 'pady': 3}

        # top spacer
        self.components.Frame(dlg, height=6).pack(fill=tk.X)

        # ---- task_id ----
        f = self.components.Frame(dlg); f.pack(fill=tk.X, **P)
        self.components.Label(f, text=l['form_task_id'], font=self.components.mono_font(9),
                              fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        id_var = tk.StringVar(value=task_id or '')
        e = self.components.Entry(f, textvariable=id_var, font=self.components.mono_font(9),
                                  bg=s['card'])
        e.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=ENTRY_IPADY)

        # ---- type ----
        f = self.components.Frame(dlg); f.pack(fill=tk.X, **P)
        self.components.Label(f, text=l['form_type'], font=self.components.mono_font(9),
                              fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        type_var = tk.StringVar(value=item.get('type', 'every'))
        for t in ('once', 'every', 'daily', 'weekly', 'cron'):
            self.components.Radiobutton(
                f, text=t, variable=type_var, value=t,
                font=self.components.mono_font(9), selectcolor=s['card'],
                command=lambda: _toggle_type()).pack(side=tk.LEFT, padx=4)

        # ---- type-specific params ----
        detail = self.components.Frame(dlg)
        detail.pack(fill=tk.X, padx=22, pady=(0, 4))

        # Placeholders: real definitions follow after UI widgets are created
        _toggle_type = lambda: None
        _update_cron_preview = lambda *_: None

        every_f = self.components.Frame(detail)
        self.components.Label(every_f, text=l['form_interval'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        every_var = tk.StringVar(value=str(item.get('interval', '')))
        self.components.Entry(every_f, textvariable=every_var,
                              font=self.components.mono_font(9), bg=s['card'],
                              width=8).pack(side=tk.LEFT, padx=4, ipady=ENTRY_IPADY)

        every_start_f = self.components.Frame(detail)
        self.components.Label(every_start_f, text=l['form_start_time'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        saved_start = item.get('start_time')
        every_start_var = tk.StringVar(
            value=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(saved_start))
            if saved_start else '')
        self.components.Entry(every_start_f, textvariable=every_start_var,
                              font=self.components.mono_font(9), bg=s['card'],
                              width=18).pack(side=tk.LEFT, padx=4, ipady=ENTRY_IPADY)

        every_picker_btn = self.components.Button(
            every_start_f, text=' 🕐', font=self.components.mono_font(10),
            bg=s['bg'], fg=s['hint'], padx=6)
        every_picker_btn.pack(side=tk.LEFT)

        # inline time picker — toggles to the right of the button
        every_start_picker_f = self.components.Frame(every_start_f)
        get_every_start_time = _make_time_picker(every_start_picker_f,
            every_start_var.get() if ':' in every_start_var.get() else '',
            self.components, self._s)

        def _merge_every_start():
            picked = get_every_start_time()
            current = every_start_var.get().strip()
            if not current:
                every_start_var.set(picked)
            elif len(current) >= 19 and current[4] == '-' and current[10] == ' ':
                every_start_var.set(current[:11] + picked)
            elif len(current) == 10 and current[4] == '-':
                every_start_var.set(current + ' ' + picked)
            else:
                every_start_var.set(picked)

        self.components.Button(
            every_start_picker_f, text='✓',
            command=lambda: (_merge_every_start(),
                             every_start_picker_f.pack_forget(),
                             every_start_hint.pack(side=tk.LEFT, padx=(2, 0))),
            bg=s['accent'], fg=s['accent_fg'],
            font=self.components.mono_font(9, 'bold')).pack(side=tk.LEFT, padx=4)

        def _toggle_every_start_picker():
            if every_start_picker_f.winfo_ismapped():
                every_start_picker_f.pack_forget()
                every_start_hint.pack(side=tk.LEFT, padx=(2, 0))
            else:
                every_start_hint.pack_forget()
                every_start_picker_f.pack(side=tk.LEFT, padx=(4, 0))

        every_picker_btn.bind('<Button-1>', lambda e: _toggle_every_start_picker())

        every_start_hint = self.components.Label(every_start_f,
                                                 text=l['form_start_time_hint'],
                                                 font=self.components.mono_font(7),
                                                 fg=s['hint'])
        every_start_hint.pack(side=tk.LEFT, padx=(2, 0))

        once_f = self.components.Frame(detail)
        self.components.Label(once_f, text=l['form_delay'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        once_delay_var = tk.StringVar(value=str(item.get('delay', '')))
        self.components.Entry(once_f, textvariable=once_delay_var,
                              font=self.components.mono_font(9), bg=s['card'],
                              width=18).pack(side=tk.LEFT, padx=4, ipady=ENTRY_IPADY)

        picker_btn = self.components.Button(
            once_f, text=' 🕐', font=self.components.mono_font(10),
            bg=s['bg'], fg=s['hint'], padx=6)
        picker_btn.pack(side=tk.LEFT)

        # inline time picker — toggles to the right of the button
        once_time_f = self.components.Frame(once_f)
        get_once_time = _make_time_picker(once_time_f,
            once_delay_var.get() if ':' in once_delay_var.get() else '',
            self.components, self._s)

        def _merge_time():
            picked = get_once_time()
            current = once_delay_var.get().strip()
            if not current:
                once_delay_var.set(picked)
            elif len(current) >= 19 and current[4] == '-' and current[10] == ' ':
                once_delay_var.set(current[:11] + picked)
            elif len(current) == 10 and current[4] == '-':
                once_delay_var.set(current + ' ' + picked)
            else:
                once_delay_var.set(picked)

        self.components.Button(
            once_time_f, text='✓',
            command=lambda: (_merge_time(), once_time_f.pack_forget()),
            bg=s['accent'], fg=s['accent_fg'],
            font=self.components.mono_font(9, 'bold')).pack(side=tk.LEFT, padx=4)

        def _toggle_time_picker():
            if once_time_f.winfo_ismapped():
                once_time_f.pack_forget()
            else:
                once_time_f.pack(side=tk.LEFT, padx=(4, 0))

        picker_btn.bind('<Button-1>', lambda e: _toggle_time_picker())

        once_hint = self.components.Label(once_f, text=l['form_delay_hint'],
                                          font=self.components.mono_font(7),
                                          fg=s['hint'], anchor='w')
        once_hint.pack(fill=tk.X, padx=(4, 0), pady=(1, 2))

        daily_f = self.components.Frame(detail)
        self.components.Label(daily_f, text=l['form_time'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        daily_time = _make_time_picker(daily_f, item.get('time_str', ''),
                                       self.components, self._s)

        weekly_f = self.components.Frame(detail)
        # row 1: days
        weekly_days_f = self.components.Frame(weekly_f)
        self.components.Label(weekly_days_f, text=l['form_days'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        day_vars = {}
        saved_days = set(item.get('days') or [])
        for i, name in enumerate(_WEEKDAY_NAMES):
            day_vars[i] = tk.BooleanVar(value=i in saved_days)
            self.components.Checkbutton(
                weekly_days_f, text=name, variable=day_vars[i],
                font=self.components.mono_font(8), selectcolor=s['card']).pack(
                side=tk.LEFT, padx=2)
        weekly_days_f.pack(fill=tk.X, pady=(0, 3))
        # row 2: time
        weekly_time_f = self.components.Frame(weekly_f)
        self.components.Label(weekly_time_f, text=l['form_time'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        weekly_time = _make_time_picker(weekly_time_f, item.get('time_str', ''),
                                        self.components, self._s)
        weekly_time_f.pack(fill=tk.X)

        cron_f = self.components.Frame(detail)
        self.components.Label(cron_f, text=l['form_cron'],
                              font=self.components.mono_font(9), fg=s['hint'],
                              anchor='w', width=10).pack(side=tk.LEFT, padx=(0, 8))
        cron_var = tk.StringVar(value=item.get('cron_expr', ''))
        self.components.Entry(cron_f, textvariable=cron_var,
                              font=self.components.mono_font(9), bg=s['card'],
                              width=22).pack(side=tk.LEFT, padx=4, ipady=ENTRY_IPADY)

        cron_preview = self.components.Label(cron_f, text='',
                                             font=self.components.mono_font(7),
                                             fg=s['hint'])
        cron_preview.pack(side=tk.LEFT, padx=4)

        _type_frames = {'every': [every_f, every_start_f], 'once': once_f,
                        'daily': daily_f, 'weekly': weekly_f, 'cron': cron_f}

        def _toggle_type():
            once_time_f.pack_forget()
            for f2 in _type_frames.values():
                if isinstance(f2, list):
                    for item in f2:
                        item.pack_forget()
                else:
                    f2.pack_forget()
            sel = type_var.get()
            frames = _type_frames[sel]
            if isinstance(frames, list):
                for i, item in enumerate(frames):
                    extra = (4, 0) if i > 0 else (2, 0)
                    item.pack(fill=tk.X, pady=extra)
            else:
                frames.pack(fill=tk.X, pady=(2, 0))
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
        f = self.components.Frame(dlg); f.pack(fill=tk.X, **P)
        self.components.Label(f, text=l['form_target'], font=self.components.mono_font(9),
                              fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        fn_var = tk.StringVar(value=item.get('fn_ref', ''))
        self.components.Entry(f, textvariable=fn_var, font=self.components.mono_font(9),
                              bg=s['card']).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=ENTRY_IPADY)
        # hint aligned with input field
        target_hint_f = self.components.Frame(dlg)
        target_hint_f.pack(fill=tk.X, padx=10, pady=(1, 2))
        self.components.Label(target_hint_f, text='', font=self.components.mono_font(9),
                              width=12).pack(side=tk.LEFT)
        self.components.Label(target_hint_f, text=l['form_target_hint'],
                              font=self.components.mono_font(7), fg=s['hint'],
                              anchor='w', justify=tk.LEFT).pack(
            side=tk.LEFT, fill=tk.X, expand=True)

        # ---- args (positional) ----
        f = self.components.Frame(dlg); f.pack(fill=tk.X, **P)
        self.components.Label(f, text='Args', font=self.components.mono_font(9),
                              fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        saved_args = item.get('args', ())
        args_var = tk.StringVar(value=', '.join(saved_args) if saved_args else '')
        self.components.Entry(f, textvariable=args_var, font=self.components.mono_font(9),
                              bg=s['card']).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=ENTRY_IPADY)
        args_hint_f = self.components.Frame(dlg)
        args_hint_f.pack(fill=tk.X, padx=10, pady=(0, 2))
        self.components.Label(args_hint_f, text='', font=self.components.mono_font(9),
                              width=12).pack(side=tk.LEFT)
        self.components.Label(args_hint_f, text='逗号分隔，如: hello, 42',
                              font=self.components.mono_font(7), fg=s['hint'],
                              anchor='w').pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ---- kwargs (keyword) ----
        f = self.components.Frame(dlg); f.pack(fill=tk.X, **P)
        self.components.Label(f, text='Kwargs', font=self.components.mono_font(9),
                              fg=s['hint'], width=12, anchor='w').pack(side=tk.LEFT)
        add_kv_btn = self.components.Button(
            f, text='＋', font=self.components.mono_font(10, 'bold'),
            bg=s['bar'], fg=s['accent'], padx=6)
        add_kv_btn.pack(side=tk.RIGHT)

        # ---- options frame (declared & packed early so kv_frame can reference it) ----
        opt = self.components.Frame(dlg)
        opt.pack(fill=tk.X, **P)

        # ---- kv_frame (scrollable, show/hide with before=opt to keep position) ----
        kv_frame = self.components.Frame(dlg)
        # 滚动条常驻（auto_hide=False）— 限高临界区避免 pack 振荡卡死
        kv_canvas = self.components.ScrollableCanvas(
            kv_frame, height=0, auto_hide=False)
        kv_inner = kv_canvas.inner
        kv_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        kv_rows = []  # list of (key_var, val_var, row_frame)
        saved_kwargs = item.get('kwargs', {})
        _KV_MAX_VISIBLE = 5
        _KV_ROW_H = 26
        _last_kv_h = [None]  # 缓存上次高度，避免重复 configure 触发循环

        def _sync_kv_scroll():
            # 限高：最多显示 _KV_MAX_VISIBLE 行，超出滚动（scrollregion 与
            # 滚动条显隐由 ScrollableCanvas 自动处理）。
            # 高度不变时不 configure — 防止与 Canvas <Configure> 刷新互相触发
            kv_canvas.update_idletasks()
            bbox = kv_canvas.bbox('all')
            if bbox:
                _, _, _, h = bbox
                visible = min(len(kv_rows), _KV_MAX_VISIBLE) * _KV_ROW_H + 2
                new_h = min(h, visible)
            else:
                new_h = 0
            if new_h != _last_kv_h[0]:
                _last_kv_h[0] = new_h
                kv_canvas.configure(height=new_h)

        def _sync_kv_frame():
            if kv_rows:
                if not kv_frame.winfo_ismapped():
                    kv_frame.pack(fill=tk.X, padx=10, pady=(0, 2), before=opt)
                _sync_kv_scroll()
            else:
                kv_frame.pack_forget()

        def _add_kv_row(key='', value=''):
            row = self.components.Frame(kv_inner)
            row.pack(fill=tk.X, pady=(2, 0))
            key_var = tk.StringVar(value=key)
            val_var = tk.StringVar(value=value)
            self.components.Label(row, text='', font=self.components.mono_font(9),
                                  width=12).pack(side=tk.LEFT)
            self.components.Entry(row, textvariable=key_var,
                                  font=self.components.mono_font(9), bg=s['card'],
                                  width=12).pack(side=tk.LEFT, padx=(0, 4), ipady=ENTRY_IPADY)
            self.components.Entry(row, textvariable=val_var,
                                  font=self.components.mono_font(9), bg=s['card']).pack(
                side=tk.LEFT, fill=tk.X, expand=True, ipady=ENTRY_IPADY)
            del_btn = self.components.Button(
                row, text='✕', font=self.components.mono_font(9),
                bg=s['bg'], fg=s['danger'], padx=6)
            del_btn.pack(side=tk.RIGHT)
            del_btn.bind('<Button-1>', lambda e, r=row: _remove_kv_row(r))
            kv_rows.append((key_var, val_var, row))
            _sync_kv_frame()

        def _remove_kv_row(row):
            for i, (k, v, r) in enumerate(kv_rows):
                if r is row:
                    row.destroy()
                    kv_rows.pop(i)
                    _sync_kv_frame()
                    break

        add_kv_btn.bind('<Button-1>', lambda e: _add_kv_row())

        if saved_kwargs:
            for k, v in saved_kwargs.items():
                _add_kv_row(k, v)

        # ---- options ----

        auto_var = tk.BooleanVar(value=item.get('auto_start', True))
        self.components.Checkbutton(
            opt, text=l['form_auto_start'], variable=auto_var,
            font=self.components.mono_font(9), selectcolor=s['card']).pack(side=tk.LEFT, padx=2)

        max_runs_frame = self.components.Frame(opt)
        max_runs_frame.pack(side=tk.LEFT)
        self.components.Label(max_runs_frame,
                              text=f'  {l["form_max_runs"]}',
                              font=self.components.mono_font(9),
                              fg=s['hint']).pack(side=tk.LEFT)
        max_var = tk.StringVar(value=str(item.get('max_runs', '') if item.get('max_runs') else ''))
        self.components.Entry(max_runs_frame, textvariable=max_var,
                              font=self.components.mono_font(9), bg=s['card'],
                              width=5).pack(side=tk.LEFT, padx=2, ipady=ENTRY_IPADY)

        timeout_lbl = self.components.Label(opt, text='  Timeout(s)',
                                             font=self.components.mono_font(9),
                                             fg=s['hint'])
        timeout_lbl.pack(side=tk.LEFT, padx=(10, 2))
        timeout_var = tk.StringVar(value=str(item.get('timeout', '') if item.get('timeout') else ''))
        self.components.Entry(opt, textvariable=timeout_var,
                              font=self.components.mono_font(9), bg=s['card'],
                              width=5).pack(side=tk.LEFT, padx=2, ipady=ENTRY_IPADY)

        # ---- buttons ----
        bf = self.components.Frame(dlg)
        bf.pack(fill=tk.X, padx=10, pady=(8, 10))
        err_var = tk.StringVar(value='')
        self.components.Label(bf, textvariable=err_var,
                              font=self.components.mono_font(8, 'bold'),
                              fg=s['danger'], anchor='w').pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        # 最右按钮右缘与上方内容区右缘对齐（右 padx 0）
        self.components.Button(
            bf, text=l['form_cancel'], command=dlg.destroy,
            bg=s['bar']).pack(side=tk.RIGHT, padx=(4, 0))
        self.components.Button(
            bf, text=l['form_save'], command=lambda: _save()).pack(side=tk.RIGHT, padx=4)

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
                    st_val = every_start_var.get().strip()
                    result = self._srv('create_every', tid, fv, fn,
                              auto_start=au, max_runs=mr, timeout=to,
                              updating=editing, args=task_args, kwargs=task_kwargs,
                              start_time=st_val if st_val else None)
                elif tp == 'once':
                    val = once_delay_var.get().strip()
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
                self._sync_display()
            except (ValueError, KeyError) as exc:
                err_var.set(str(exc)[:60])

        _toggle_type()
        dlg.update_idletasks()
        w = dlg.winfo_reqwidth()
        max_h = int(self.winfo_screenheight() * 0.85)
        dlg.minsize(w, 1)
        dlg.maxsize(w, max_h)
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

    def on_destroy(self):
        pass
