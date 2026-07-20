# -*- coding: utf-8 -*-
"""Inspector plugin — event / store / services flow map."""
import time
import tkinter as tk

from plugins.plugin import PluginBase

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


class Inspector(PluginBase):
    name = "Inspector"
    name_zh = "审查器"
    name_en = "Inspector"
    namespace = "inspector"
    priority = 99
    reload = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        theme_name = getattr(app, 'current_theme_name', 'dark')
        self._s = _STYLE.get(theme_name, _STYLE['dark'])
        s = self._s

        self.title(self.name)
        self.geometry("520x520")
        self.resizable(True, True)
        self.configure(bg=s['bg'])

        # ---- header ----
        header = tk.Frame(self, bg=s['bar'], height=32)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        tk.Label(header, text="  Inspector", bg=s['bar'], fg=s['fg'],
                 font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT, pady=4)

        self._status = tk.Label(header, text="", bg=s['bar'],
                                fg=s['hint'], font=("Consolas", 8))
        self._status.pack(side=tk.RIGHT, padx=8, pady=4)

        # ---- tab bar ----
        self._tabs = {}
        self._active_tab = None
        tab_bar = tk.Frame(self, bg=s['bg'], height=30)
        tab_bar.pack(fill=tk.X, side=tk.TOP, padx=6, pady=(4, 0))
        tab_bar.pack_propagate(False)

        for key, label in [("events", "Events"), ("store", "Store"), ("services", "Services")]:
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

        tk.Frame(self, bg=s['accent'], height=2).pack(fill=tk.X, side=tk.TOP, padx=6)

        # ---- content ----
        content = tk.Frame(self, bg=s['bg'])
        content.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 2))

        self._frames = {}
        self._texts = {}
        for key in ("events", "store", "services"):
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
            self._frames[key] = frm
            self._texts[key] = txt

        # ---- footer ----
        bar = tk.Frame(self, bg=s['bar'], height=32)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self._filter_var = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text=" All events",
                       variable=self._filter_var, command=self._refresh,
                       bg=s['bar'], fg=s['fg'], font=("Microsoft YaHei", 8),
                       selectcolor=s['bar'], relief=tk.FLAT,
                       activebackground=s['bar'], activeforeground=s['fg']
                       ).pack(side=tk.LEFT, padx=8, pady=4)

        tk.Button(bar, text=" Refresh ", command=self._refresh,
                  bg=s['accent'], fg=s['accent_fg'],
                  font=("Microsoft YaHei", 9, "bold"),
                  relief=tk.FLAT, padx=14, borderwidth=0,
                  activebackground='#3a6fa8', activeforeground='#ffffff'
                  ).pack(side=tk.RIGHT, padx=4, pady=4)

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

    def on_show(self):
        self._refresh()

    # ---- refresh ----

    def _refresh(self):
        infra = self.app._infra
        self._render_events(infra)
        self._render_store(infra)
        self._render_services(infra)
        self._status.config(text=time.strftime("%H:%M:%S"))

    # ---- events flow ----

    def _render_events(self, infra):
        listeners = infra.eventbus._listeners
        namespaced = infra.eventbus._namespaced

        ns_map = {}
        for ns, pairs in namespaced.items():
            for event, cb in pairs:
                ns_map.setdefault(event, {})[cb] = ns

        show_all = self._filter_var.get()
        active = {}
        for e, c in listeners.items():
            if not c:
                continue
            if not show_all and e not in ns_map:
                continue
            active[e] = c

        lines = [
            "  ACTIVE EVENTS: " + str(len(active)),
            "",
        ]

        for event in sorted(active.keys()):
            cbs = active[event]
            ns_info = ns_map.get(event, {})
            lines.append(f"  ● {event}")
            for i, cb in enumerate(cbs):
                ns = ns_info.get(cb, '-')
                prefix = "    └─" if i == len(cbs) - 1 else "    ├─"
                lines.append(f"{prefix} [{ns}] {self._cb_name(cb)}")
            lines.append("")

        self._set_text(self._texts["events"], lines)

    # ---- store flow ----

    def _render_store(self, infra):
        state = infra.store._state
        owners = infra.store._owners
        subs = infra.store._subscriptions

        by_owner = {}
        for k, v in state.items():
            owner = owners.get(k, '-')
            by_owner.setdefault(owner, []).append((k, v))

        lines = ["  TOTAL KEYS: " + str(len(state)), ""]

        for owner in sorted(by_owner.keys()):
            lines.append(f"  ● [{owner}]")
            items = by_owner[owner]
            for i, (k, v) in enumerate(items):
                val = str(v)[:80]
                prefix = "    └─" if i == len(items) - 1 else "    ├─"
                lines.append(f"{prefix} {k} = {val}")
                event = f'store:changed:{k}'
                for sub_owner, pairs in subs.items():
                    for ev, cb in pairs:
                        if ev == event and sub_owner != owner:
                            lines.append(f"    │  ← subscribed by [{sub_owner}] {self._cb_name(cb)}")
            lines.append("")

        self._set_text(self._texts["store"], lines)

    # ---- services flow ----

    def _render_services(self, infra):
        svc = infra.services._services
        owners = infra.services._owners

        by_owner = {}
        for name in svc:
            owner = owners.get(name, '-')
            by_owner.setdefault(owner, []).append(name)

        lines = ["  TOTAL SERVICES: " + str(len(svc)), ""]

        for owner in sorted(by_owner.keys()):
            lines.append(f"  ● [{owner}]")
            names = sorted(by_owner[owner])
            for i, name in enumerate(names):
                prefix = "    └─" if i == len(names) - 1 else "    ├─"
                lines.append(f"{prefix} {name}")
            lines.append("")

        self._set_text(self._texts["services"], lines)

    @staticmethod
    def _cb_name(cb):
        if hasattr(cb, '__self__') and hasattr(cb, '__func__'):
            return f'{type(cb.__self__).__name__}.{cb.__func__.__name__}'
        try:
            return cb.__qualname__
        except AttributeError:
            return repr(cb)[:40]

    def _set_text(self, widget, lines):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert("1.0", "\n".join(lines))
        widget.config(state=tk.DISABLED)
