# -*- coding: utf-8 -*-
"""
Agent 设置窗口 — 端点列表管理
"""
import copy
import re
import uuid
import tkinter as tk

from .config import find_api_key

LANG = {
    'zh': {
        'title': 'Agent 配置',
        'col_name': '名称', 'col_url': '端点', 'col_model': '模型', 'col_key': 'API KEY',
        'add': '新增', 'delete': '删除',
        'save': '保存', 'cancel': '取消',
        'err_no_rows': '没有可用端点, 请先添加',
        'err_dup_name': '存在同名端点 "%s", 请修改名称后再保存',
        'confirm_unsaved': '端点配置已修改但未保存, 是否保存?\n\n"是" 保存并关闭, "否" 放弃修改',
    },
    'en': {
        'title': 'Agent Configuration',
        'col_name': 'Name', 'col_url': 'Base URL', 'col_model': 'Models', 'col_key': 'API KEY',
        'add': 'Add', 'delete': 'Delete',
        'save': 'Save', 'cancel': 'Cancel',
        'err_no_rows': 'No endpoints available, add one first',
        'err_dup_name': 'Duplicate endpoint name "%s", rename it before saving',
        'confirm_unsaved': 'Endpoints modified but not saved. Save now?\n\nYes = save and close, No = discard',
    },
}


class _BaseRow:
    """一行端点条目: 勾选 + 名称/端点/key 三个输入框."""

    def __init__(self, parent, c, theme, data=None, build_in=False, sync_header_func=None):
        self.build_in = build_in
        data = data or {}
        self.unique_id = data.get('id') or uuid.uuid4().hex
        self.sel = tk.BooleanVar(value=False)
        if build_in:
            self.cb = c.Label(parent, text='', bg=theme['bar'])
        else:
            self.cb = c.Checkbutton(parent, bg=theme['bar'], variable=self.sel, font=c.mono_font(7))
            if sync_header_func:
                self.sel.trace_add('write', lambda *_: sync_header_func())
        self.name = c.Entry(parent, width=15, font=c.mono_font(9))
        self.name.insert(0, str(data.get('name', '')))
        self.url = c.Entry(parent, width=30, font=c.mono_font(9))
        self.url.insert(0, str(data.get('url', '')))
        if build_in:
            self.name.config(state=tk.DISABLED, disabledbackground=theme['bar'])
            self.url.config(state=tk.DISABLED, disabledbackground=theme['bar'])
        self.models = c.Entry(parent, width=30, font=c.mono_font(9))
        models = ','.join(data.get('models', []))
        self.models.insert(0, models)
        self.key = c.Entry(parent, width=40, font=c.mono_font(9))
        api_key = data.get('api_key', '')
        if not api_key and data and data.get('url', ''):
            _key, _ = find_api_key(data['url'])
            if _key:
                self.key.insert(0, '******')
                self.key.config(show='*')
        else:
            self.key.insert(0, str(api_key))

    def grid(self, row):
        self.cb.grid(row=row, column=0)
        self.name.grid(row=row, column=1, sticky='ew', ipady=3, padx=(2, 4))
        self.url.grid(row=row, column=2, sticky='ew', ipady=3, padx=(0, 4))
        self.models.grid(row=row, column=3, sticky='ew', ipady=3, padx=(0, 4))
        self.key.grid(row=row, column=4, sticky='ew', ipady=3, padx=(0, 8))

    def destroy(self):
        for w in (self.cb, self.name, self.url, self.models, self.key):
            w.destroy()

    def data(self):
        """收集本行输入 — url 去尾斜杠 (与预设格式一致)."""
        api_key = self.key.get().strip()
        if api_key == '******':
            api_key = ''
        result = re.split(r'[,;]', self.models.get().strip())
        models = [model.strip() for model in result if model.strip()]
        return {
            'id': self.unique_id,
            'name': self.name.get().strip(),
            'url': self.url.get().strip().rstrip('/'),
            'models': models,
            'api_key': api_key
        }


class AgentSettingsWindow:
    """主题化二级窗口 — 通过 owner (AgentPanel) 与主面板联动."""

    def __init__(self, owner, providers, default_providers):
        self._owner = owner
        self._l = LANG.get(owner.app.current_lang_name, LANG['en'])
        self.theme = t = owner.app.theme
        self._rows = []
        self.win = owner.components.Toplevel(owner)
        self.win.title(self._l['title'])
        self.win.resizable(True, False)
        self.win.configure(bg=t['bar'])
        self.win.transient(owner)
        self.win.bind('<Destroy>', self._on_destroy)
        self._providers = providers
        self._default_providers = default_providers
        # 初始快照 — 保存时对比跳过无效保存; 关闭时据此判断未保存改动
        self._orig_providers = copy.deepcopy(providers)
        self.win.protocol('WM_DELETE_WINDOW', self._on_close)

        self._build_ui()
        owner.app.emit('app@window:set-geometry', self.win, w=660, h=420)

    def _build_ui(self):
        c, t, l = self._owner.components, self._owner.app.theme, self._l

        top = c.Frame(self.win, bg=t['bar'])
        top.pack(fill=tk.X, padx=8, pady=(10, 6))

        # ---- 新增 / 删除 ----
        self.btn_del = c.Button(top, text=l['delete'], pady=1, state=tk.DISABLED, bg=t['Button']['disabled_bg'], command=self._delete_selected)
        self.btn_del.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.btn_add = c.Button(top, text=l['add'], pady=1, command=self._add_row)
        self.btn_add.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(6, 0))

        header = c.Frame(self.win, bg=t['bar'])
        header.pack(fill=tk.X, padx=0, pady=(10, 6))

        hf = c.mono_font(9)
        self._header_sel = tk.BooleanVar(value=False)
        self._header_cb = c.Checkbutton(
            header, bg=t['bar'], variable=self._header_sel,
            font=c.mono_font(7), command=self._toggle_all)
        self._header_cb.grid(row=0, column=0)
        c.Label(header, bg=t['bar'], text=l['col_name'], fg=t['hint'],
                font=hf, anchor='w', width=15).grid(row=0, column=1, sticky='w')
        c.Label(header, bg=t['bar'], text=l['col_url'], fg=t['hint'],
                font=hf, anchor='w', width=30).grid(row=0, column=2, sticky='w')
        c.Label(header, bg=t['bar'], text=l['col_model'], fg=t['hint'],
                font=hf, anchor='w', width=30).grid(row=0, column=3, sticky='w')
        c.Label(header, bg=t['bar'], text=l['col_key'], fg=t['hint'],
                font=hf, anchor='w', width=40).grid(row=0, column=4, sticky='w')
        header.columnconfigure(2, weight=3)   # 端点
        header.columnconfigure(3, weight=3)   # models
        header.columnconfigure(4, weight=4)   # key

        # ---- 表头 + 行区 (header + rows 共享一个 grid, 行区可滚动) ----
        wrap = c.Frame(self.win, bg=t['bar'])
        wrap.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 4))
        canvas = c.ScrollableCanvas(wrap, bg=t['bar'], height=1,
                                    highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        inner = canvas.inner
        self._rows_frame = inner
        # inner.columnconfigure(1, weight=1)   # 名称
        inner.columnconfigure(2, weight=3)   # 端点
        inner.columnconfigure(3, weight=3)   # models
        inner.columnconfigure(4, weight=4)   # key

        for i, item in enumerate(self._providers):
            self._add_row(item, build_in=i < len(self._default_providers))

        # ---- 默认端点 + 保存/取消 ----
        bar = c.Frame(self.win, bg=t['bar'])
        bar.pack(fill=tk.X, padx=10, pady=(6, 6))
        c.Button(bar, text=l['save'],
                 command=self._save).pack(side=tk.RIGHT, fill=tk.X, expand=True)

    # ---- 行管理 ----
    def _sync_header(self):
        """Header reflects the rows: checked only when all deletable rows are
        checked; disabled when only built-in (undeletable) rows exist."""
        deletable = [r for r in self._rows if not r.build_in]
        all_checked = bool(deletable) and all(r.sel.get() for r in deletable)
        any_checked = any(r.sel.get() for r in deletable)
        self._header_sel.set(all_checked)
        self._header_cb.config(
            state=tk.NORMAL if deletable else tk.DISABLED)
        if any_checked:
            self.btn_del.config(state=tk.NORMAL, bg=self.theme['danger'])
        else:
            self.btn_del.config(state=tk.DISABLED,
                                bg=self.theme['Button']['disabled_bg'])

    def _add_row(self, data=None, build_in=False):
        row = _BaseRow(self._rows_frame, self._owner.components,
                       self._owner.app.theme, data, build_in, sync_header_func=self._sync_header)
        self._rows.append(row)
        self._reindex()
        self._sync_header()
        return row

    def _reindex(self):
        for i, row in enumerate(self._rows):
            row.grid(i)

    def _delete_selected(self):
        keep_rows = []
        del_rows = []
        for r in self._rows:
            if r.sel.get():
                del_rows.append(r)
            else:
                keep_rows.append(r)
        if len(keep_rows) == len(self._rows):
            return
        for r in del_rows:
            r.destroy()
        self._rows = keep_rows
        self._sync_header()
        self._reindex()
        self._header_sel.set(False)

    def _toggle_all(self):
        v = self._header_sel.get()
        for r in self._rows:
            if not r.build_in:
                r.sel.set(v)

    # ---- 保存 / 关闭 ----

    def _collect(self):
        """收集全部行数据 — 与 _BaseRow.data() 同形, 供保存与脏对比共用."""
        providers = []
        for r in self._rows:
            d = r.data()
            if not d['url']:
                continue
            if not d['name']:
                d['name'] = d['url']
            providers.append(d)
        return providers

    def _is_dirty(self):
        return self._collect() != self._orig_providers

    def _save(self):
        providers = self._collect()
        if not providers:
            self._owner.components.showwarning(
                self._l['title'], self._l['err_no_rows'], parent=self.win)
            return
        # 同名检测 — provider 按 name 匹配, 重名会导致匹配歧义
        seen = set()
        for d in providers:
            if d['name'] in seen:
                self._owner.components.showwarning(
                    self._l['title'], self._l['err_dup_name'] % d['name'],
                    parent=self.win)
                return
            seen.add(d['name'])
        # 快照对比 — 无改动直接关窗, 跳过写盘/reload (避免聊天区噪音)
        if providers == self._orig_providers:
            self.win.destroy()
            return
        self._owner.on_settings_save(providers)
        self.win.destroy()

    def _on_close(self):
        """点 X 关闭 — 有未保存改动时弹窗确认 (同 ui/settings.py 模式)."""
        if self._is_dirty():
            answer = self._owner.components.askyesnocancel(
                self._l['title'], self._l['confirm_unsaved'], parent=self.win)
            if answer is None:      # 取消 — 留在窗口
                return
            if answer:              # 是 — 走保存流程 (校验失败会留在窗口)
                self._save()
                return
        self.win.destroy()          # 否 / 无改动 — 直接关闭

    def _on_destroy(self, event):
        if event.widget is self.win:
            self._owner.on_settings_closed()
