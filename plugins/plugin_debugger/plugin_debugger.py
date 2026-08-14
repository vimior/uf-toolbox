# -*- coding: utf-8 -*-
"""Plugin Debugger plugin — interactive REPL with plugin-system access.

The namespace is pre-populated so users can drive the whole toolbox:
  - ``app`` — the plugin-system proxy (services / store / events / after)
  - ``self`` — this plugin instance
  - ``attach(ns)`` — read-only proxy for operating another plugin's namespace

Magic commands (prefix ``?``) shortcut the most common introspection:
  ?help  ?services  ?store  ?eventbus  ?clear  ?reset

Output area tags: 'in' (echoed input), 'out' (stdout), 'err' (stderr /
tracebacks), 'sys' (timing / reset notices), 'magic' (magic output).
"""
import code
import time
import tkinter as tk
import traceback
from contextlib import redirect_stderr, redirect_stdout

from plugins.plugin import GuiPlugin

LANG = {
    'zh': {
        'title': '插件调试器',
        'btn_clear': '清空',
        'btn_help': '帮助',
        'btn_reset': '重置',
        'prelude_vars': '内置变量: app (插件框架: 服务/事件/状态), self (本插件), attach (只读操作其他插件)',
        'prelude_magic': '魔法命令: ?help, ?services, ?store, ?eventbus, ?clear, ?reset',
        'magic_unknown': '未知命令: {cmd} — 输入 ?help 查看帮助',
        'reset_done': '解释器已重置, 命名空间已重建',
        'no_services': '(没有已注册的服务)',
        'store_empty': '(store 为空)',
        'eventbus_empty': '(没有活跃的事件)',
        'exit_hint': '[exit 不会关闭窗口 — 点窗口右上角 X 关闭, 插件可随时从菜单重新打开]',
        'help_title': '=== 帮助 ===',
        'help_magic': '魔法命令:',
        'help_magic_list': '  ?help                显示本帮助\n'
                           '  ?services [ns]       列出服务 (不带参数为全部)\n'
                           '  ?store [ns]          列出状态键 (不带参数为全部)\n'
                           '  ?eventbus [ns]       列出活跃事件 (不带参数为全部)\n'
                           '  ?clear               清空输出区\n'
                           '  ?reset               重置解释器与命名空间',
        'help_examples': '常用示例:',
        'help_ex_list': "  app.services.names()\n"
                        "  app.services.call('demo_service@add', 1, 2)\n"
                        "  app.store.get('key')\n"
                        "  app.emit('demo_service@current_time', {'time': '12:00:00'})\n"
                        "  app.after(1000, lambda: print('tick'))",
        'help_attach_title': 'attach 用法 (只读代理):',
        'help_attach_list': "  net = attach('net_tools')\n"
                            "  net.services.names()\n"
                            "  net.services.call('ping', '192.168.1.1')\n"
                            "  net.store.get('key')\n"
                            "  net.eventbus.on('scan_done', cb)",
        'help_attach_warn': '注意: 代理不含写入能力 (commit/emit/register)',
        'help_note': '注意: 代码在主线程执行, 耗时操作会暂时阻塞界面',
    },
    'en': {
        'title': 'Plugin Debugger',
        'btn_clear': 'Clear',
        'btn_help': 'Help',
        'btn_reset': 'Reset',
        'prelude_vars': 'Built-in vars: app (plugin framework: services/events/store), self (this plugin), attach (read-only access to other plugins)',
        'prelude_magic': 'Magic commands: ?help, ?services, ?store, ?eventbus, ?clear, ?reset',
        'magic_unknown': 'Unknown command: {cmd} — try ?help',
        'reset_done': 'Interpreter reset, namespace rebuilt',
        'no_services': '(no registered services)',
        'store_empty': '(store is empty)',
        'eventbus_empty': '(no active events)',
        'exit_hint': '[exit does not close the window — use the window close button, reopen from the menu anytime]',
        'help_title': '=== Help ===',
        'help_magic': 'Magic commands:',
        'help_magic_list': '  ?help               show this help\n'
                           '  ?services [ns]      list services (all without ns)\n'
                           '  ?store [ns]         list state keys (all without ns)\n'
                           '  ?eventbus [ns]      list active events (all without ns)\n'
                           '  ?clear              clear the output area\n'
                           '  ?reset              reset the interpreter and namespace',
        'help_examples': 'Examples:',
        'help_ex_list': "  app.services.names()\n"
                        "  app.services.call('demo_service@add', 1, 2)\n"
                        "  app.store.get('key')\n"
                        "  app.emit('demo_service@current_time', {'time': '12:00:00'})\n"
                        "  app.after(1000, lambda: print('tick'))",
        'help_attach_title': 'attach (read-only proxy):',
        'help_attach_list': "  net = attach('net_tools')\n"
                            "  net.services.names()\n"
                            "  net.services.call('ping', '192.168.1.1')\n"
                            "  net.store.get('key')\n"
                            "  net.eventbus.on('scan_done', cb)",
        'help_attach_warn': 'Note: no write paths on the proxy (commit/emit/register)',
        'help_note': 'Note: code runs on the main thread; long tasks will block the UI briefly',
    },
}


class _ReadonlyEventbus:
    """Read-only eventbus view — on / off only (no emit / clear)."""

    __slots__ = ('_m',)

    def __init__(self, module):
        self._m = module

    def on(self, event, callback):
        return self._m.on(event, callback)

    def off(self, event, callback):
        return self._m.off(event, callback)


class _ReadonlyServices:
    """Read-only services view — names / has / call only."""

    __slots__ = ('_m',)

    def __init__(self, module):
        self._m = module

    def names(self):
        return self._m.names()

    def has(self, name):
        return self._m.has(name)

    def call(self, name, *args, **kwargs):
        return self._m.call(name, *args, **kwargs)


class _ReadonlyStore:
    """Read-only store view — get / keys only."""

    __slots__ = ('_m',)

    def __init__(self, module):
        self._m = module

    def get(self, key, default=None):
        return self._m.get(key, default)

    def keys(self):
        return self._m.keys()


class _ReadonlyProxy:
    """Read-only view of another plugin's namespaced handle.

    ``eventbus`` / ``services`` / ``store`` are exposed as read-only
    sub-views, so the API shape matches the framework's own namespaced
    handle.  Write paths (store commit, emit, register, cleanup) are
    intentionally not exposed — reaching them requires the raw
    ``app._infra.module(...)``.
    """

    def __init__(self, module):
        self.eventbus = _ReadonlyEventbus(module.eventbus)
        self.services = _ReadonlyServices(module.services)
        self.store = _ReadonlyStore(module.store)
        self.namespace = module._ns


class _TagWriter:
    """File-like sink forwarding writes to the console with a text tag."""

    __slots__ = ('_console', '_tag')

    def __init__(self, console, tag):
        self._console = console
        self._tag = tag

    def write(self, data):
        if data:
            self._console.write_tagged(data, self._tag)

    def flush(self):
        pass


class _Console(code.InteractiveConsole):
    """InteractiveConsole whose output lands in the tkinter Text widget.

    ``runsource`` wraps execution with stdout/stderr redirection, so
    ``print`` / tracebacks appear in the output area with proper tags.
    Returns True while a multi-line statement is still incomplete.
    """

    def __init__(self, on_write, namespace):
        super().__init__(locals=namespace)
        self._on_write = on_write

    # ---- output sink (also used by showsyntaxerror / showtraceback) ----

    def write(self, data):
        # Called by the interpreter for syntax errors / tracebacks only.
        self._on_write(data, 'err')

    def write_tagged(self, data, tag):
        # Called by _TagWriter with an explicit tag (stdout / stderr).
        self._on_write(data, tag)

    # ---- execute with redirection ----

    def runsource(self, source, filename='<console>', symbol='single'):
        out = _TagWriter(self, 'out')
        err = _TagWriter(self, 'err')
        try:
            with redirect_stdout(out), redirect_stderr(err):
                more = super().runsource(source, filename, symbol)
        except SystemExit as exc:
            # user-requested exit — an informational notice, not an error
            self._on_write(f'[SystemExit: {exc.code}]\n', 'sys')
            more = False
        except BaseException:
            # compile()/runsource edge cases we don't expect — keep the
            # REPL alive instead of letting tkinter's callback swallow it
            self._on_write(traceback.format_exc(), 'err')
            more = False
        return more


class PluginDebugger(GuiPlugin):
    """Interactive Python REPL window for exploring the toolbox."""

    name = "Plugin Debugger"
    name_zh = "插件调试器"
    name_en = "Plugin Debugger"
    namespace = "plugin_debugger"
    priority = 996
    reload = True
    fixed_position = False
    fixed_size = False

    def __init__(self, parent=None, app=None):
        super().__init__(parent, app)
        self._l = LANG.get(self.app.current_lang_name, LANG['en'])
        t = self.app.theme

        self.title(self._l['title'])
        self.resizable(True, True)
        self.configure(bg=t['bar'])

        self._history = []
        self._hist_idx = -1
        self._more = False   # True while a multi-line statement is pending

        # ---- toolbar ----
        bar = self.components.Frame(self, bg=t['bar'], height=32)
        bar.pack(fill=tk.X, side=tk.TOP, pady=(2, 2))
        bar.pack_propagate(False)
        for key, cmd in (('clear', self._clear), ('help', self._help),
                         ('reset', self._reset)):
            self.components.Button(
                bar, text=self._l[f'btn_{key}'],
                command=cmd).pack(side=tk.RIGHT, padx=(2, 8), pady=2)

        # ---- output area (own frame so the scrollbars pack beside the
        # text, not among the window-level children) ----
        out_frame = self.components.Frame(self, bg=t['bar'])
        out_frame.pack(fill=tk.BOTH, expand=True, padx=8)
        self._out = self.components.ScrollableText(
            out_frame, font=self.components.mono_font(10), wrap=tk.WORD)
        self._out.pack(fill=tk.BOTH, expand=True, padx=(0, 8))
        self._out.config(state=tk.DISABLED)
        self._out.tag_configure('in', foreground=t['accent'])
        self._out.tag_configure('out', foreground=t['fg'])
        self._out.tag_configure('err', foreground=t['danger'])
        self._out.tag_configure('sys', foreground=t['hint'])
        self._out.tag_configure('magic', foreground=t['accent'])

        # ---- input line ----
        bottom = self.components.Frame(self, bg=t['bar'])
        bottom.pack(fill=tk.X, padx=8, pady=8)
        self._prompt_label = self.components.Label(
            bottom, text='>>> ', font=self.components.mono_font(10),
            bg=t['bar'], fg=t['hint'], padx=0)
        self._prompt_label.pack(side=tk.LEFT)
        self._entry = self.components.Entry(
            bottom, font=self.components.mono_font(10))
        self._entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        self._entry.bind('<Return>', self._on_submit)
        self._entry.bind('<Up>', self._on_hist)
        self._entry.bind('<Down>', self._on_hist)
        self._entry.focus_set()

        self._console = _Console(self._write, self._build_namespace())
        self._write_prelude()
        self.app.emit('app@window:set-geometry', self, w=720, h=520)

    # ---- output helpers ----

    def _write(self, data, tag='out'):
        w = self._out
        w.config(state=tk.NORMAL)
        w.insert(tk.END, data, tag)
        w.config(state=tk.DISABLED)
        w.see(tk.END)

    def _write_prelude(self):
        lines = (
            f"# {self._l['title']}",
            '',
            f"  {self._l['prelude_vars']}",
            f"  {self._l['prelude_magic']}",
            '',
        )
        self._write('\n'.join(lines) + '\n', 'sys')

    def _echo_prompt(self):
        self._prompt_label.config(text='... ' if self._more else '>>> ')

    # ---- namespace ----

    def _build_namespace(self):
        def attach(ns):
            """Read-only proxy for another plugin's namespace.

            Call its services, read its state, watch its events — the
            same API shape as the framework's namespaced handle, minus
            every write path (commit / emit / register / cleanup).
            """
            return _ReadonlyProxy(self.app._infra.module(ns, app=self.app._app))

        return {
            'app': self.app,
            'self': self,
            'attach': attach,
            '__name__': '__plugin_debugger__',
        }

    # ---- input handling ----

    def _on_submit(self, _event=None):
        source = self._entry.get()
        self._entry.delete(0, tk.END)
        if not source.strip():
            prompt = '... ' if self._more else '>>> '
            self._write(f'{prompt}\n', 'in')
            if self._more:
                # blank line finishes a pending compound statement
                # (for/def blocks execute only after an empty line,
                # same as the native REPL)
                self._more = self._console.push('')
                self._echo_prompt()
            return 'break'
        self._history.append(source)
        self._hist_idx = -1

        prompt = '... ' if self._more else '>>> '
        self._write(f'{prompt}{source}\n', 'in')

        stripped = source.strip()
        if stripped.startswith('?'):
            self._run_magic(stripped)
            self._echo_prompt()
            return 'break'
        if stripped in ('exit', 'exit()', 'quit', 'quit()'):
            self._write(self._l['exit_hint'] + '\n', 'sys')
            return 'break'

        t0 = time.perf_counter()
        # push() buffers continuation lines and re-runs the whole block
        self._more = self._console.push(source)
        if not self._more:
            elapsed = (time.perf_counter() - t0) * 1000
            self._write(f'[{elapsed:.1f} ms]\n', 'sys')
        self._echo_prompt()
        return 'break'

    def _on_hist(self, event):
        if not self._history:
            return 'break'
        if event.keysym == 'Up':
            if self._hist_idx == -1:
                self._hist_idx = len(self._history) - 1
            elif self._hist_idx > 0:
                self._hist_idx -= 1
        else:
            if self._hist_idx == -1:
                return 'break'
            self._hist_idx += 1
            if self._hist_idx >= len(self._history):
                self._hist_idx = -1
                self._entry.delete(0, tk.END)
                return 'break'
        self._entry.delete(0, tk.END)
        self._entry.insert(0, self._history[self._hist_idx])
        return 'break'

    # ---- magic commands ----

    def _run_magic(self, cmd):
        parts = cmd.split()
        name = parts[0][1:].lower()
        ns = parts[1] if len(parts) > 1 else None
        if name in ('help', '?', ''):
            self._help()
        elif name == 'services':
            self._magic_services(ns)
        elif name == 'store':
            self._magic_store(ns)
        elif name == 'eventbus':
            self._magic_eventbus(ns)
        elif name == 'clear':
            self._clear()
        elif name == 'reset':
            self._reset()
        else:
            self._write(self._l['magic_unknown'].format(cmd=name) + '\n', 'err')

    def _magic_services(self, ns=None):
        names = self.app._infra.services.names(ns)
        if not names:
            self._write(self._l['no_services'] + '\n', 'magic')
            return
        for n in sorted(names):
            self._write(f'  {n}\n', 'magic')

    def _magic_store(self, ns=None):
        store = self.app._infra.store
        keys = store.keys(ns)
        if not keys:
            self._write(self._l['store_empty'] + '\n', 'magic')
            return
        for k in sorted(keys):
            self._write(f'  {k} = {store.get(k)!r}\n', 'magic')

    def _magic_eventbus(self, ns=None):
        events = self.app._infra.eventbus.events(ns)
        if not events:
            self._write(self._l['eventbus_empty'] + '\n', 'magic')
            return
        for e in sorted(events):
            self._write(f'  {e}\n', 'magic')

    def _help(self):
        l = self._l
        self._write('\n' + l['help_title'] + '\n\n', 'magic')
        self._write(l['prelude_vars'] + '\n\n', 'magic')
        self._write(l['help_magic'] + '\n' + l['help_magic_list'] + '\n\n', 'magic')
        self._write(l['help_examples'] + '\n' + l['help_ex_list'] + '\n\n', 'magic')
        self._write(l['help_attach_title'] + '\n' + l['help_attach_list'] + '\n\n', 'magic')
        self._write(l['help_attach_warn'] + '\n\n', 'sys')
        self._write(l['help_note'] + '\n', 'sys')

    # ---- toolbar actions ----

    def _clear(self):
        w = self._out
        w.config(state=tk.NORMAL)
        w.delete('1.0', tk.END)
        w.config(state=tk.DISABLED)

    def _reset(self):
        self._console = _Console(self._write, self._build_namespace())
        self._more = False
        self._write(self._l['reset_done'] + '\n', 'sys')
        self._echo_prompt()
        self._entry.focus_set()
