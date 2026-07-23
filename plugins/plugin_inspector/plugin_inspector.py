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

_STYLE = {
    'dark': {
        'bg':        '#2b2b2b',
        'bar':       '#333333',
        'text_bg':   '#363636',
        'fg':        '#e0e0e0',
        'hint':      '#888888',
        'hover':     '#4a4a4a',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
    },
    'light': {
        'bg':        '#f5f5f5',
        'bar':       '#e0e0e0',
        'text_bg':   '#ffffff',
        'fg':        '#333333',
        'hint':      '#999999',
        'hover':     '#d0d0d0',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
    },
}


class PluginInspector(GuiPlugin):
    name = "Plugin Inspector"
    name_zh = "插件审查器"
    name_en = "Plugin Inspector"
    namespace = "plugin_inspector"
    priority = 998
    reload = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        lang_name = self.app.current_lang_name
        theme_name = self.app.current_theme_name
        self._lbl = _LANG.get(lang_name, _LANG['en'])
        self._s = _STYLE.get(theme_name, _STYLE['dark'])
        s = self._s

        self.title(self.name_zh if lang_name == 'zh' else self.name_en)
        self.geometry("666x520")
        self.resizable(True, True)
        self.configure(bg=s['bg'])

        # ---- tab bar ----
        self._tabs = {}
        self._active_tab = None
        tab_bar = tk.Frame(self, bg=s['bg'], height=30)
        tab_bar.pack(fill=tk.X, side=tk.TOP, padx=6, pady=(4, 0))
        tab_bar.pack_propagate(False)

        for key in ("events", "store", "services", "perf"):
            label = self._lbl[key]
            btn = tk.Label(tab_bar, text=f" {label} ", font=("Microsoft YaHei", 10),
                           bg=s['bg'], fg=s['fg'], padx=14, pady=3,
                           cursor="hand2", relief=tk.FLAT)
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda _, k=key: self._switch_tab(k))
            btn.bind("<Enter>", lambda _, b=btn: b.config(bg=s['hover']))
            btn.bind("<Leave>",
                     lambda _, b=btn, k=key:
                     b.config(bg=s['accent'] if self._active_tab == k else s['bg']))
            self._tabs[key] = btn

        self._status = tk.Label(tab_bar, text="", bg=s['bg'],
                                fg=s['hint'], font=("Consolas", 8))
        self._status.pack(side=tk.RIGHT, padx=8, pady=4)

        tk.Frame(self, bg=s['accent'], height=2).pack(fill=tk.X, side=tk.TOP, padx=6)

        # ---- content ----
        content = tk.Frame(self, bg=s['bg'])
        content.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 2))

        self._frames = {}
        self._texts = {}
        for key in ("events", "store", "services", "perf"):
            frm = tk.Frame(content, bg=s['bg'])
            frm.pack(fill=tk.BOTH, expand=True)
            frm.pack_forget()
            txt = tk.Text(frm, wrap=tk.NONE, state=tk.DISABLED,
                          font=("Consolas", 9),
                          bg=s['text_bg'], fg=s['fg'],
                          insertbackground=s['fg'],
                          relief=tk.FLAT, borderwidth=0,
                          padx=10, pady=6)
            txt.pack(fill=tk.BOTH, expand=True)

            def _scroll(event, t=txt):
                t.yview_scroll(int(-1 * (event.delta / 120)), "units")
            txt.bind("<MouseWheel>", _scroll)

            self._frames[key] = frm
            self._texts[key] = txt

        # ---- footer ----
        bar = tk.Frame(self, bg=s['bar'], height=32)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        lbl = self._lbl
        self._filter_var = tk.BooleanVar(value=False)
        self._filter_cb = tk.Checkbutton(bar, text=lbl['all_events'],
                       variable=self._filter_var, command=self._refresh,
                       bg=s['bar'], fg=s['fg'], font=("Microsoft YaHei", 8),
                       selectcolor=s['bar'], relief=tk.FLAT,
                       activebackground=s['bar'], activeforeground=s['fg'])

        self._auto_refresh_var = tk.BooleanVar(value=False)
        self._auto_refresh_job = None
        self._auto_refresh_cb = tk.Checkbutton(bar, text=lbl['auto_refresh'],
                       variable=self._auto_refresh_var, command=self._toggle_auto_refresh,
                       bg=s['bar'], fg=s['fg'], font=("Microsoft YaHei", 8),
                       selectcolor=s['bar'], relief=tk.FLAT,
                       activebackground=s['bar'], activeforeground=s['fg'])
        self._auto_refresh_cb.pack(side=tk.LEFT, padx=2, pady=4)

        self._interval_var = tk.StringVar(value='2s')
        self._interval_btn = tk.Menubutton(
            bar, bg=s['bar'], fg=s['fg'], font=("Consolas", 9),
            relief=tk.FLAT, padx=6, pady=1, borderwidth=0,
            activebackground=s['hover'], activeforeground=s['fg'],
            cursor='hand2')
        self._interval_btn.pack(side=tk.LEFT, padx=2, pady=4)
        menu = tk.Menu(self._interval_btn, tearoff=0, bg=s['text_bg'], fg=s['fg'],
                       font=("Consolas", 9),
                       activebackground=s['accent'], activeforeground=s['accent_fg'])
        for val in _REFRESH_INTERVALS:
            menu.add_radiobutton(label=val, variable=self._interval_var, value=val,
                                command=self._on_interval_changed)
        self._interval_btn.configure(menu=menu)
        self._interval_btn.configure(text=f"{self._interval_var.get()} ▾")
        self._interval_var.trace_add('write',
            lambda *_: self._interval_btn.configure(text=f"{self._interval_var.get()} ▾"))

        tk.Button(bar, text=lbl['refresh'], command=self._refresh,
                  bg=s['accent'], fg=s['accent_fg'],
                  font=("Microsoft YaHei", 9, "bold"),
                  relief=tk.FLAT, padx=14, borderwidth=0,
                  activebackground='#3a6fa8', activeforeground='#ffffff'
                  ).pack(side=tk.RIGHT, padx=4, pady=4)

        self._perf_reset_btn = tk.Button(bar, text=lbl['perf_reset'],
                  command=self._perf_reset,
                  bg=s['bar'], fg=s['fg'],
                  font=("Microsoft YaHei", 8),
                  relief=tk.FLAT, padx=10, borderwidth=0,
                  activebackground=s['hover'], activeforeground=s['fg']
                  )
        self._perf_reset_btn.pack(side=tk.RIGHT, padx=2, pady=4)
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

        active = {}
        plugin_cb_count = 0
        app_cb_count = 0

        for event, info in all_events.items():
            callbacks = info['callbacks']
            if show_all:
                visible = callbacks
            else:
                if not callbacks:
                    continue
                visible = [e for e in callbacks if e['namespace'] != 'app']
                if not visible:
                    continue
            active[event] = (info, visible)
            for e in visible:
                if e['namespace'] == 'app':
                    app_cb_count += 1
                else:
                    plugin_cb_count += 1

        if show_all:
            header = f"  ACTIVE EVENTS: {len(active)}  CALLBACKS: {plugin_cb_count + app_cb_count} (PLUGINS: {plugin_cb_count}, APP: {app_cb_count})"
        else:
            header = f"  ACTIVE EVENTS: {len(active)}  PLUGIN CALLBACKS: {plugin_cb_count}"
        lines = [header, ""]

        for event in sorted(active.keys()):
            info, callbacks = active[event]
            stats = []
            if info['count']:
                stats.append(f"{info['count']} emits")
            if info['last_emit']:
                stats.append(f"last {self._time_str(info['last_emit'])}")
            line = f"  ● {event}"
            if stats:
                line += f"    {_PREFIX}{'  '.join(stats)}"
            lines.append(line)
            if not callbacks:
                lines.append("")
                continue
            for i, entry in enumerate(callbacks):
                prefix = "    └─" if i == len(callbacks) - 1 else "    ├─"
                name = entry['name']
                if entry['namespace'] != 'app':
                    dot = name.find('.')
                    if dot != -1:
                        name = name[dot + 1:]
                line = f"{prefix} [{entry['namespace']}] {name}"
                if entry['since']:
                    line += f"  [{self._time_str(entry['since'])}]"
                lines.append(line)
            lines.append("")

        self._set_text(self._texts["events"], lines)

    # ---- store flow ----

    def _render_store(self, infra):
        data = infra.store.snapshot()
        keys = data['keys']

        by_owner = {}
        for entry in keys:
            owner = entry['owner']
            by_owner.setdefault(owner, []).append(entry)

        lines = ["  TOTAL KEYS: " + str(len(keys)), ""]

        for owner in sorted(by_owner.keys()):
            lines.append(f"  ● [{owner}]")
            items = by_owner[owner]
            for i, entry in enumerate(items):
                prefix = "    └─" if i == len(items) - 1 else "    ├─"
                bar = " " if i == len(items) - 1 else "│"
                short = entry['key']
                pfx = owner + '.'
                if short.startswith(pfx):
                    short = short[len(pfx):]
                lines.append(f"{prefix} {short} = {entry['value']}")
                stats = []
                if entry['commit_count']:
                    stats.append(f"{entry['commit_count']} commits")
                if entry['last_commit']:
                    stats.append(f"last {self._time_str(entry['last_commit'])}")
                if stats:
                    lines.append(f"    {bar}    {'  '.join(stats)}")
                for sub in entry['subscribers']:
                    if sub != owner:
                        lines.append(f"    {bar}    ← {sub}")
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

        lines = ["  TOTAL SERVICES: " + str(len(services)), ""]

        for owner in sorted(by_owner.keys()):
            lines.append(f"  ● [{owner}]")
            items = sorted(by_owner[owner], key=lambda e: e['name'])
            for i, entry in enumerate(items):
                prefix = "    └─" if i == len(items) - 1 else "    ├─"
                bar = " " if i == len(items) - 1 else "│"
                short = entry['name']
                pfx = owner + '.'
                if short.startswith(pfx):
                    short = short[len(pfx):]
                line = f"{prefix} {short}  [{self._time_str(entry['since'])}]" if entry['since'] else f"{prefix} {short}"
                lines.append(line)
                stats = []
                if entry['call_count']:
                    stats.append(f"{entry['call_count']} calls")
                if entry['last_call']:
                    stats.append(f"last {self._time_str(entry['last_call'])}")
                if stats:
                    lines.append(f"    {bar}    {'  '.join(stats)}")
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

        # ---- totals ----
        t = s['totals']
        lines.append(f"  {_PREFIX}Event emits:      {t['event_calls']}    {t['event_total_s']*1000:.2f} ms")
        lines.append(f"  {_PREFIX}Service calls:    {t['service_calls']}    {t['service_total_s']*1000:.2f} ms")
        lines.append(f"  {_PREFIX}Store commits:    {t['store_commits']}")
        lines.append(f"  {_PREFIX}Store subscribes: {t['store_subscribes']}")
        lines.append("")

        # ---- per-namespace ----
        ns_data = s['namespaces']
        if not ns_data:
            lines.append("  (no activity recorded yet)")
        else:
            for ns, data in ns_data.items():
                events = data['events']
                services = data['services']
                store = data['store']

                ev_total_s = sum(v['total_s'] for v in events.values())
                ev_count = sum(v['count'] for v in events.values())
                sv_total_s = sum(v['total_s'] for v in services.values())
                sv_count = sum(v['count'] for v in services.values())

                lines.append(f"  ● [{ns}]")
                if ev_count:
                    lines.append(f"    {_PREFIX}Events:   {ev_count} emits, {ev_total_s*1000:.2f} ms")
                if sv_count:
                    lines.append(f"    {_PREFIX}Services: {sv_count} calls, {sv_total_s*1000:.2f} ms")
                if store.get('commits') or store.get('subscribes'):
                    lines.append(f"    {_PREFIX}Store:    {store.get('commits',0)} commits, {store.get('subscribes',0)} subscribes")

                # Top slowest events for this namespace
                if events:
                    ranked = sorted(events.items(), key=lambda x: x[1]['total_s'], reverse=True)
                    shown = 0
                    for ev_name, ev_data in ranked:
                        if ev_data['count'] == 0:
                            continue
                        max_ms = ev_data['max_s'] * 1000
                        if max_ms < 0.1 and ev_data['total_s'] * 1000 < 0.5:
                            continue
                        avg_ms = (ev_data['total_s'] / ev_data['count']) * 1000
                        lines.append(f"      {_PREFIX}{ev_name}    {ev_data['count']} emits  avg {avg_ms:.2f}ms  max {max_ms:.2f}ms")
                        shown += 1
                        if shown >= 5:
                            remaining = len(ranked) - shown
                            if remaining > 0:
                                lines.append(f"      {_PREFIX}... and {remaining} more")
                            break
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
