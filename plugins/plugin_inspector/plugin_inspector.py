# -*- coding: utf-8 -*-
"""Inspector plugin — event / store / services flow map."""
import time
import tkinter as tk
from plugins.plugin import GuiPlugin

_PREFIX = '- '  # category stat-line prefix (perf tab)
_REFRESH_INTERVALS = ('1s', '2s', '5s', '10s', '30s')

_LANG = {
    'zh': {
        'events':   '事件',
        'store':    '存储',
        'services': '服务',
        'perf':     '性能',
        'all_events': ' 全部事件',
        'auto_refresh': ' 自动刷新',
        'refresh':  ' 刷新 ',
        'perf_reset': ' 清零 ',
    },
    'en': {
        'events':   'Events',
        'store':    'Store',
        'services': 'Services',
        'perf':     'Perf',
        'all_events': ' All events',
        'auto_refresh': ' Auto-refresh',
        'refresh':  ' Refresh ',
        'perf_reset': ' Reset ',
    },
}

class PluginInspector(GuiPlugin):
    name = "Plugin Inspector"
    name_zh = "插件审查器"
    name_en = "Plugin Inspector"
    namespace = "plugin_inspector"
    priority = 997
    reload = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        lang_name = self.app.current_lang_name
        self._lbl = _LANG.get(lang_name, _LANG['en'])
        self._s = self.app.theme
        s = self._s

        self.title(self.name_zh if lang_name == 'zh' else self.name_en)
        self.geometry("688x520")
        self.resizable(True, True)

        # ---- tab bar ----
        self._tabs = {}
        self._active_tab = None
        tab_bar = self.components.Frame(self, bg=s['bar'], height=32)
        tab_bar.pack(fill=tk.X, side=tk.TOP)
        tab_bar.pack_propagate(False)

        for key in ("events", "store", "services", "perf"):
            label = self._lbl[key]
            btn = self.components.Label(
                tab_bar, text=f" {label} ", font=self.components.font(10),
                padx=14, pady=3)
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda _, k=key: self._switch_tab(k))
            btn.bind("<Enter>", lambda _, b=btn: b.config(bg=s['hover']))
            btn.bind("<Leave>",
                     lambda _, b=btn, k=key:
                     b.config(bg=s['accent'] if self._active_tab == k else s['bg']))
            self._tabs[key] = btn

        self._status = self.components.Label(tab_bar, text="", bg=s['bar'],
                                             fg=s['hint'], font=self.components.mono_font(8))
        self._status.pack(side=tk.RIGHT, padx=8, pady=4)

        self.components.Frame(self, bg=s['accent'], height=2).pack(
            fill=tk.X, side=tk.TOP)

        # ---- content ----
        content = self.components.Frame(self)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))

        self._frames = {}
        self._texts = {}
        for key in ("events", "store", "services", "perf"):
            frm = self.components.Frame(content)
            frm.pack(fill=tk.BOTH, expand=True)
            frm.pack_forget()
            txt = self.components.ScrollableText(
                frm, wrap=tk.NONE, state=tk.DISABLED, scrollbars='both')
            txt.pack(fill=tk.BOTH, expand=True)
            # 滚轮由 ScrollableText 内置（Enter/Leave 全局绑定）

            self._frames[key] = frm
            self._texts[key] = txt

        # ---- footer ----
        # bar 贴窗口边缘；bar 内按钮自带右 8 边距（与上方内容区右缘对齐）
        bar = self.components.Frame(self, bg=s['bar'], height=32)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        lbl = self._lbl
        self._filter_var = tk.BooleanVar(value=False)
        self._filter_cb = self.components.Checkbutton(
            bar, text=lbl['all_events'],
            variable=self._filter_var, command=self._refresh,
            bg=s['bar'], selectcolor=s['bar'],
            font=self.components.font(8))

        self._auto_refresh_var = tk.BooleanVar(value=False)
        self._auto_refresh_job = None
        self._auto_refresh_cb = self.components.Checkbutton(
            bar, text=lbl['auto_refresh'],
            variable=self._auto_refresh_var, command=self._toggle_auto_refresh,
            bg=s['bar'], selectcolor=s['bar'],
            font=self.components.font(8))
        self._auto_refresh_cb.pack(side=tk.LEFT, padx=2, pady=4)

        self._interval_var = tk.StringVar(value='2s')
        self._interval_btn = self.components.Menubutton(
            bar, bg=s['bar'], fg=s['fg'], font=self.components.mono_font(9),
            relief=tk.FLAT, padx=6, pady=1, borderwidth=0,
            activebackground=s['hover'], activeforeground=s['fg'],
            cursor='hand2')
        self._interval_btn.pack(side=tk.LEFT, padx=2, pady=4)
        menu = self.components.Menu(
            self._interval_btn,
            activebackground=s['accent'], activeforeground=s['accent_fg'])
        for val in _REFRESH_INTERVALS:
            menu.add_radiobutton(label=val, variable=self._interval_var, value=val,
                                command=self._on_interval_changed)
        self._interval_btn.configure(menu=menu)
        self._interval_btn.configure(text=f"{self._interval_var.get()} ▾")
        self._interval_var.trace_add('write',
            lambda *_: self._interval_btn.configure(text=f"{self._interval_var.get()} ▾"))

        self.components.Button(
            bar, text=lbl['refresh'],
            command=self._refresh).pack(side=tk.RIGHT, padx=(6, 8), pady=4)

        self._perf_reset_btn = self.components.Button(
            bar, text=lbl['perf_reset'], command=self._perf_reset)
        self._perf_reset_btn.pack(side=tk.RIGHT, padx=6, pady=4)
        self._perf_reset_btn.pack_forget()  # hidden by default, shown on perf tab

        self._switch_tab("events")

    def _switch_tab(self, key):
        s = self._s
        for k, btn in self._tabs.items():
            if k == key:
                btn.config(bg=s['accent'], fg=s['accent_fg'])
                self._frames[k].pack(fill=tk.BOTH, expand=True)
            else:
                btn.config(bg=s['bg'], fg=s['fg'])
                self._frames[k].pack_forget()
        self._active_tab = key
        # Tab-specific footer controls
        if key == 'perf':
            self._perf_reset_btn.pack(side=tk.RIGHT, padx=2, pady=4)
        else:
            self._perf_reset_btn.pack_forget()
        if key == 'events':
            self._filter_cb.pack(side=tk.LEFT, padx=(16, 4), pady=4, after=self._interval_btn)
        else:
            self._filter_cb.pack_forget()

    def on_show(self):
        self._refresh()

    def on_destroy(self):
        """Cancel auto-refresh timer before teardown."""
        if self._auto_refresh_job is not None:
            self.after_cancel(self._auto_refresh_job)
            self._auto_refresh_job = None

    # ---- refresh ----

    def _toggle_auto_refresh(self):
        if self._auto_refresh_var.get():
            self._auto_refresh_tick()
        elif self._auto_refresh_job is not None:
            self.after_cancel(self._auto_refresh_job)
            self._auto_refresh_job = None

    def _auto_refresh_tick(self):
        if not self._auto_refresh_var.get():
            return
        if not self.winfo_exists():
            return
        self._refresh()
        ms = int(self._interval_var.get().rstrip('s')) * 1000
        self._auto_refresh_job = self.after(ms, self._auto_refresh_tick)

    def _on_interval_changed(self, _event=None):
        """Restart timer if auto-refresh is on and interval changes."""
        if not self._auto_refresh_var.get():
            return
        if self._auto_refresh_job is not None:
            self.after_cancel(self._auto_refresh_job)
            self._auto_refresh_job = None
        self._auto_refresh_tick()

    def _refresh(self):
        infra = self.app._infra
        self._render_events(infra)
        self._render_store(infra)
        self._render_services(infra)
        self._render_perf(infra)
        self._status.config(text=time.strftime("%H:%M:%S"))

    # ---- events flow ----

    def _render_events(self, infra):
        data = infra.eventbus.snapshot()
        all_events = data['events']
        show_all = self._filter_var.get()

        # group events by namespace (first @ prefix)
        grouped = {}  # ns → [(event_name, info, cbs), ...]
        for event, info in all_events.items():
            cbs = info['callbacks']
            if not show_all:
                cbs = [e for e in cbs if e['namespace'] != 'app']
                ns = event.partition('@')[0]
                if ns in ('app', 'plugins', 'services', 'tasks', 'agent'):
                    if not cbs:
                        continue
                    if info['count'] == 0 and all(cb['count'] == 0 for cb in cbs):
                        continue
                elif info['count'] == 0 and not cbs:
                    continue
            ns, _, local = event.partition('@')
            grouped.setdefault(ns if _ else '-', []).append((local or event, info, cbs))

        total_emits = sum(v[1]['count'] for g in grouped.values() for v in g)
        total_cbs = sum(len(v[2]) for g in grouped.values() for v in g)
        total_events = sum(len(g) for g in grouped.values())
        lines = [f"  EVENTS: {total_events}  EMITS: {total_emits}  CALLBACKS: {total_cbs}", ""]

        for ns in sorted(grouped.keys()):
            items = grouped[ns]
            lines.append(f"  ● [{ns}]")
            for ei, (event, info, cbs) in enumerate(sorted(items, key=lambda x: x[0])):
                is_last_ns_event = (ei == len(items) - 1)
                ns_bar = "   " if is_last_ns_event else "  │"
                e_prefix = "  └─" if is_last_ns_event else "  ├─"
                lines.append(f"  {e_prefix} {event}")
                ec = info['count']
                cc = len(cbs)
                # emits
                emit_ns = info.get('emit_ns', [])
                if ec or emit_ns:
                    last = self._time_str(info['last_emit']) if info.get('last_emit') else '-'
                    lines.append(f"  {ns_bar}    emits: {ec}  last {last}")
                    for i, o in enumerate(emit_ns):
                        o_prefix = "├─" if i < len(emit_ns) - 1 else "└─"
                        o_last = self._time_str(o['last_emit']) if o.get('last_emit') else '-'
                        lines.append(f"  {ns_bar}      {o_prefix} [{o['namespace']}]  ×{o['count']}  last {o_last}")
                # callbacks
                if cbs:
                    lines.append(f"  {ns_bar}    callbacks: {cc}")
                    for i, entry in enumerate(cbs):
                        c_prefix = "├─" if i < len(cbs) - 1 else "└─"
                        name = entry['name']
                        if entry['namespace'] != 'app':
                            dot = name.find('.')
                            if dot != -1:
                                name = name[dot + 1:]
                        count = entry.get('count', 0)
                        since = self._time_str(entry['since']) if entry.get('since') else '-'
                        lines.append(f"  {ns_bar}      {c_prefix} [{entry['namespace']}] {name}  ×{count}  [{since}]")
                if not is_last_ns_event:
                    lines.append(f"  {ns_bar}")
            lines.append("")

        self._set_text(self._texts["events"], lines)

    # ---- store flow ----

    def _render_store(self, infra):
        data = infra.store.snapshot()
        keys = data['keys']
        # index eventbus callbacks by event for subscriber lookup
        evt_data = infra.eventbus.snapshot()['events']
        evt_callbacks = {e: e_info['callbacks'] for e, e_info in evt_data.items()}

        by_owner = {}
        for entry in keys:
            owner = entry['owner']
            by_owner.setdefault(owner, []).append(entry)

        lines = [f"  KEYS: {len(keys)}  OWNERS: {len(by_owner)}", ""]

        for owner in sorted(by_owner.keys()):
            lines.append(f"  ● [{owner}]")
            items = by_owner[owner]
            for i, entry in enumerate(items):
                prefix = "  ├─" if i < len(items) - 1 else "  └─"
                is_last = (i == len(items) - 1)
                bar = "   " if is_last else "  │"
                short = entry['key']
                pfx = owner + '@'
                if short.startswith(pfx):
                    short = short[len(pfx):]
                lines.append(f"{prefix} {short} = {entry['value']}")
                stats = []
                if entry['commit_count']:
                    stats.append(f"{entry['commit_count']} commits")
                if entry['last_commit']:
                    stats.append(f"last {self._time_str(entry['last_commit'])}")
                if stats:
                    lines.append(f"  {bar}  {'  '.join(stats)}")
                # cross-ns subscribers (from eventbus snapshot)
                ext_subs = [s for s in evt_callbacks.get(f'store:changed:{entry["key"]}', [])
                            if s['namespace'] != owner]
                if ext_subs:
                    lines.append(f"  {bar}  subscribers: {len(ext_subs)}")
                    for j, sub in enumerate(ext_subs):
                        s_prefix = "├─" if j < len(ext_subs) - 1 else "└─"
                        cb_name = sub['name'].split('.')[-1] if '.' in sub['name'] else sub['name']
                        lines.append(f"  {bar}    {s_prefix} [{sub['namespace']}] {cb_name}  ×{sub['count']}")
            lines.append("")

        self._set_text(self._texts["store"], lines)

    # ---- services flow ----

    def _render_services(self, infra):
        data = infra.services.snapshot()
        services = data['services']

        by_owner = {}
        for entry in services:
            owner = entry['owner']
            by_owner.setdefault(owner, []).append(entry)

        lines = [f"  SERVICES: {len(services)}  OWNERS: {len(by_owner)}", ""]

        for owner in sorted(by_owner.keys()):
            lines.append(f"  ● [{owner}]")
            items = sorted(by_owner[owner], key=lambda e: e['name'])
            for i, entry in enumerate(items):
                prefix = "  ├─" if i < len(items) - 1 else "  └─"
                short = entry['name']
                pfx = owner + '@'
                if short.startswith(pfx):
                    short = short[len(pfx):]
                is_last = (i == len(items) - 1)
                bar = "   " if is_last else "  │"
                since = self._time_str(entry['since']) if entry.get('since') else '-'
                lines.append(f"  {prefix} {short}  [{since}]")
                callers = entry.get('callers', [])
                c_total = entry.get('call_count', 0)
                if c_total:
                    c_last = self._time_str(entry['last_call']) if entry.get('last_call') else '-'
                    lines.append(f"  {bar}  {c_total} calls  last {c_last}")
                for j, caller in enumerate(callers):
                    c_prefix = "├─" if j < len(callers) - 1 else "└─"
                    c_last_s = self._time_str(caller['last_call']) if caller.get('last_call') else '-'
                    lines.append(f"  {bar}  {c_prefix} [{caller['namespace']}]  ×{caller['count']}  last {c_last_s}")
            lines.append("")

        self._set_text(self._texts["services"], lines)

    # ---- helpers ----

    @staticmethod
    def _time_str(ts):
        """Return HH:MM:SS string for *ts* (Unix timestamp)."""
        return time.strftime('%m-%d %H:%M:%S', time.localtime(ts))

    # ---- perf ----

    def _perf_reset(self):
        """Zero all performance counters."""
        self.app._infra.perf.reset()
        self._refresh()

    def _render_perf(self, infra):
        s = infra.perf.snapshot()
        lines = []

        # ---- header ----
        uptime = s['uptime_s']
        proc = s['process']
        lines.append(f"  UPTIME: {uptime:.1f}s")
        lines.append(f"  CPU TIME: {proc['cpu_time_s']:.2f}s")
        if proc['memory_mb'] is not None:
            lines.append(f"  MEMORY: {proc['memory_mb']} MB")
        else:
            lines.append(f"  MEMORY: (psutil not installed)")
        lines.append("")
        lines.append(f"  {_PREFIX}[T: total]  [A: avg]  [M: max]")
        lines.append("")

        # ---- totals ----
        t = s['totals']
        lines.append(f"  {_PREFIX}Store:   {t['store_commits']} commits, {t['store_subscribes']} subscribes")
        lines.append(f"  {_PREFIX}Event:")
        lines.append(f"      emits:     {t['emit_calls']}  [T: {t['emit_total_s']*1000:.2f}ms]")
        lines.append(f"      callbacks: {t['callback_calls']}  [T: {t['callback_total_s']*1000:.2f}ms]")
        lines.append(f"  {_PREFIX}Service: {t['service_calls']}  [T: {t['service_total_s']*1000:.2f}ms]")
        lines.append("")

        # ---- per-namespace ----
        ns_data = s['namespaces']
        if not ns_data:
            lines.append("  (no activity recorded yet)")
        else:
            for ns, data in ns_data.items():
                callbacks = data['callbacks']
                emits = data['emits']
                services = data['services']
                store = data['store']

                em_count = sum(v['count'] for v in emits.values())
                em_total_s = sum(v['total_s'] for v in emits.values())
                cb_count = sum(v['count'] for v in callbacks.values())
                cb_total_s = sum(v['total_s'] for v in callbacks.values())
                sv_count = sum(v['count'] for v in services.values())
                sv_total_s = sum(v['total_s'] for v in services.values())

                lines.append(f"  ● [{ns}]")
                if store.get('commits') or store.get('subscribes'):
                    lines.append(f"    {_PREFIX}Store:   {store.get('commits',0)} commits, {store.get('subscribes',0)} subscribes")
                if em_count or cb_count:
                    lines.append(f"    {_PREFIX}Event:")
                    if em_count:
                        lines.append(f"      emits:     {em_count}  [T: {em_total_s*1000:.2f}ms]")
                        for ev_name, ev_data in sorted(emits.items()):
                            t_ms = ev_data['total_s'] * 1000
                            avg_ms = (ev_data['total_s'] / ev_data['count']) * 1000
                            max_ms = ev_data['max_s'] * 1000
                            lines.append(f"        {_PREFIX}{ev_name}    ×{ev_data['count']}  [T: {t_ms:.2f}ms]  [A: {avg_ms:.2f}ms]  [M: {max_ms:.2f}ms]")
                    if cb_count:
                        lines.append(f"      callbacks: {cb_count}  [T: {cb_total_s*1000:.2f}ms]")
                        ranked = sorted(callbacks.items(), key=lambda x: x[1]['total_s'], reverse=True)
                        for ev_name, ev_data in ranked:
                            if ev_data['count'] == 0:
                                continue
                            t_ms = ev_data['total_s'] * 1000
                            avg_ms = (ev_data['total_s'] / ev_data['count']) * 1000
                            max_ms = ev_data['max_s'] * 1000
                            lines.append(f"        {_PREFIX}{ev_name}    ×{ev_data['count']}  [T: {t_ms:.2f}ms]  [A: {avg_ms:.2f}ms]  [M: {max_ms:.2f}ms]")
                if sv_count:
                    lines.append(f"    {_PREFIX}Service: {sv_count}  [T: {sv_total_s*1000:.2f}ms]")
                    for sv_name, sv_data in sorted(services.items()):
                        t_ms = sv_data['total_s'] * 1000
                        avg_ms = (sv_data['total_s'] / sv_data['count']) * 1000
                        max_ms = sv_data['max_s'] * 1000
                        lines.append(f"      {_PREFIX}{sv_name}    ×{sv_data['count']}  [T: {t_ms:.2f}ms]  [A: {avg_ms:.2f}ms]  [M: {max_ms:.2f}ms]")
                lines.append("")

        self._set_text(self._texts["perf"], lines)

    def _set_text(self, widget, lines):
        # Remember scroll fraction to avoid jumping on refresh
        try:
            frac = widget.yview()[0]
        except (tk.TclError, IndexError):
            frac = 0.0
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", "\n".join(lines))
        widget.config(state=tk.DISABLED)
        # Restore after tk has finished layout
        widget.after_idle(lambda f=frac: widget.yview_moveto(f))
