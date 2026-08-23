# -*- coding: utf-8 -*-
"""Plugin manager — discovery, lazy-loading, lifecycle, hot-reload."""
import ast
import os
import sys
import time
import pkgutil
import threading
import importlib.util
from typing import Literal

from plugins.plugin import GuiPlugin, HookInfo, ServicePlugin

NS = 'plugins'


class NamespaceManager:
    _RESERVED = set(['app', NS, 'services', 'tasks', 'agent', 'notify'])
    _USED = set([])

    @classmethod
    def add(cls, ns, reserved=False):
        if reserved:
            cls._RESERVED.add(ns)
        else:
            cls._USED.add(ns)

    @classmethod
    def remove(cls, ns):
        if ns in cls._USED:
            cls._USED.remove(ns)

    @classmethod
    def check(cls, ns):
        if ns in cls._RESERVED:
            raise ValueError(f'namespace({ns}) conflict [Reserved], please change the namespace.')
        if ns in cls._USED:
            raise ValueError(f'namespace({ns}) conflict [Used], please change the namespace.')

    @classmethod
    def update(cls, ns_used):
        if ns_used != cls._USED:
            cls._USED = ns_used

    @classmethod
    def is_reserved(cls, ns):
        return ns in cls._RESERVED


class PluginManager:
    """Manages plugin discovery, loading, lifecycle, and hot-reload.

    Usage::

        from common.common import logger
        pm = PluginManager(logger)
        pm.load(app, path=app.plugin_path)
        # pm.plugins is the {name: Handle} registry
    """

    META_KEYS = ('name', 'name_zh', 'name_en', 'namespace',
                 'priority', 'fixed_position', 'fixed_size', 'use_app_icon',
                 'reload', 'auto_start', 'start_hidden')

    # ---- inner handle class ------------------------------------------------

    class Handle:
        """Lazy handle — defers import + instantiation until start() is called.

        When *cls* is None (lazy mode), the plugin module is imported on first use.
        Otherwise it behaves eagerly (legacy / reload path)."""

        __slots__ = ('fixed_position', 'fixed_size', 'use_app_icon',
                     'reload', 'priority', 'auto_start', 'start_hidden',
                     '_cls', 'app', '_inst', '_pkg_dir', '_module_name',
                     '_class_name', '_mgr', '_shown',
                     '_name_raw', '_name_zh', '_name_en', '_src_mtime', '_key',
                     '_namespace', '_builtin', '_agent_tools', '_last_error')

        def __init__(self, cls, app, mgr, pkg_dir=None, module_name=None,
                     class_name=None, metadata=None, key=None, builtin=False):
            self.app = app
            self._mgr = mgr
            self._cls = cls
            self._inst = None
            self._pkg_dir = pkg_dir
            self._module_name = module_name
            self._class_name = class_name
            self._shown = False
            self._builtin = builtin
            self._name_raw = None
            self._name_zh = None
            self._name_en = None
            self._src_mtime = 0
            self._key = key
            self._namespace = None
            self._agent_tools = None
            self._last_error = None   # 最近一次 start 失败原因 (供 agent 回显)

            if cls is not None:
                # Eager — class attributes are available directly
                self._agent_tools = getattr(cls, 'agent_tools', None)
                self._name_raw = cls.name
                self._name_zh = getattr(cls, 'name_zh', None)
                self._name_en = getattr(cls, 'name_en', None)
                self._namespace = getattr(cls, 'namespace', None)
                self.priority = cls.priority
                self.auto_start = getattr(cls, 'auto_start', False)
                self.start_hidden = getattr(cls, 'start_hidden', False)
                if issubclass(cls, GuiPlugin):
                    self.reload = cls.reload
                    self.fixed_position = cls.fixed_position
                    self.fixed_size = cls.fixed_size
                    self.use_app_icon = cls.use_app_icon
                else:
                    self.reload = True
                    self.fixed_position = False
                    self.fixed_size = False
                    self.use_app_icon = False
            else:
                # Lazy — use metadata from AST parsing (or defaults)
                meta = metadata or {}
                self._agent_tools = meta.get('agent_tools')
                self._name_raw = meta.get('name') or module_name or 'Unnamed'
                self._name_zh = meta.get('name_zh')
                self._name_en = meta.get('name_en')
                self._namespace = meta.get('namespace')
                self.fixed_position = meta.get('fixed_position', True)
                self.fixed_size = meta.get('fixed_size', True)
                self.use_app_icon = meta.get('use_app_icon', True)
                self.reload = meta.get('reload', True)
                self.priority = meta.get('priority', 0)
                self.auto_start = meta.get('auto_start', False)
                self.start_hidden = meta.get('start_hidden', False)

        @property
        def is_service(self):
            return self._cls is not None and issubclass(self._cls, ServicePlugin)

        @property
        def alive(self):
            if self._inst is None:
                return False
            if isinstance(self._inst, ServicePlugin):
                return True
            return self._inst.winfo_exists()

        @property
        def loaded(self):
            """True after the plugin module has been imported."""
            return self._cls is not None

        @property
        def namespace(self):
            """Effective namespace — class attr / AST metadata → registry key."""
            if self._namespace:
                return self._namespace
            return self._key or self._module_name or 'unknown'

        def hide(self):
            """Hide a visible GUI plugin window (no-op for ServicePlugin)."""
            if self._inst is None or self.is_service:
                return
            if not self._inst.winfo_exists():
                return
            name = self.get_name()
            self.app.emit('hook:will-hide', HookInfo.from_handle(self), ns=NS)
            try:
                self._inst.on_hide()
            except Exception as e:
                self._mgr.logger.error(
                    f'[Plugin:{name}] on_hide error: {e}')
            try:
                self._inst.withdraw()
            except Exception:
                pass
            self._shown = False
            self.app.emit('hook:did-hide', HookInfo.from_handle(self), ns=NS)

        def show(self):
            """Show a hidden GUI plugin window (no-op for ServicePlugin)."""
            if self._inst is None or self.is_service:
                return
            if not self._inst.winfo_exists():
                return
            name = self.get_name()
            self._inst.deiconify()
            self._inst.lift()
            self._inst.focus_force()
            self.app.emit('hook:will-show', HookInfo.from_handle(self), ns=NS)
            try:
                self._inst.on_show()
            except Exception as e:
                self._mgr.logger.error(
                    f'[Plugin:{name}] on_show error: {e}')
            self._shown = True
            self.app.emit('hook:did-show', HookInfo.from_handle(self), ns=NS)

        @property
        def visible(self):
            """True if this GUI plugin window is currently viewable."""
            if self._inst is None or self.is_service:
                return False
            return self._inst.winfo_exists() and self._inst.winfo_viewable()

        @staticmethod
        def _start(inst):
            if isinstance(inst, ServicePlugin):
                inst.on_start()
            else:
                inst.on_show()

        @staticmethod
        def _stop(inst):
            if isinstance(inst, ServicePlugin):
                inst.on_stop()
            else:
                inst.on_destroy()

        def unload(self):
            """Call on_destroy, destroy window, clean sys.path, reset to lazy state."""
            if self._inst is not None:
                is_service = isinstance(self._inst, ServicePlugin)
                if is_service:
                    self.app.emit('hook:will-stop', HookInfo.from_handle(self), ns=NS)
                elif self._inst.winfo_exists():
                    self.app.emit('hook:will-destroy', HookInfo.from_handle(self), ns=NS)
                if is_service or self._inst.winfo_exists():
                    try:
                        self._stop(self._inst)
                    except Exception as e:
                        action = 'on_stop' if is_service else 'on_destroy'
                        self._mgr.logger.error(
                            f'Plugin {self.get_name()} {action} error: {e}')
                    if is_service:
                        self.app.emit('hook:did-stop', HookInfo.from_handle(self), ns=NS)
                    else:
                        self.app.emit('hook:did-destroy', HookInfo.from_handle(self), ns=NS)
                    if not is_service:
                        try:
                            self._inst.destroy()
                        except Exception:
                            pass
                self._inst = None
                self._shown = False
                NamespaceManager.remove(self.namespace)
            if self._pkg_dir is not None and self._pkg_dir in sys.path:
                sys.path.remove(self._pkg_dir)
            # Reset so next click re-imports (hot-reload)
            self._cls = None
            # Third-party plugins only: drop sys.modules entries so the module
            # (and its globals) can be garbage-collected. Built-in plugins are
            # imported directly by app code — clearing them would risk a second
            # module instance (e.g. plugin_guide is also imported by menu.py).
            if not self._builtin:
                self._mgr._clear_module_cache(self._module_name)

        def stop(self):
            """Destroy the plugin instance. Does NOT clear _cls.

            Use this for explicit close/reload from the UI — keeps the imported
            class so the next start() can instantiate without re-importing.
            """
            if self._inst is not None:
                is_service = isinstance(self._inst, ServicePlugin)
                if is_service:
                    self.app.emit('hook:will-stop', HookInfo.from_handle(self), ns=NS)
                elif self._inst.winfo_exists():
                    self.app.emit('hook:will-destroy', HookInfo.from_handle(self), ns=NS)
                if is_service or self._inst.winfo_exists():
                    try:
                        self._stop(self._inst)
                    except Exception as e:
                        action = 'on_stop' if is_service else 'on_destroy'
                        self._mgr.logger.error(
                            f'[Plugin:{self.get_name()}] {action} error: {e}')
                    if is_service:
                        self.app.emit('hook:did-stop', HookInfo.from_handle(self), ns=NS)
                    else:
                        self.app.emit('hook:did-destroy', HookInfo.from_handle(self), ns=NS)
                    if not is_service:
                        try:
                            self._inst.destroy()
                        except Exception:
                            pass
                self._inst = None
                self._shown = False
                NamespaceManager.remove(self.namespace)

        def close(self):
            """Destroy the plugin window (unified close semantics).

            Third-party plugins are fully unloaded — class dropped and module
            removed from sys.modules — so their memory is released; built-in
            plugins keep the class for a fast restart."""
            if self._builtin:
                self.stop()
            else:
                self.unload()

        def restart(self, parent):
            """Force destroy + recreate the plugin window (dev-time hot-reload)."""
            self.stop()
            return self.start(parent)

        def get_name(self, lang=None):
            """Return the display name for *lang* (defaults to current app language).

            Pure method — reads stored metadata, no side effects.
            """
            if lang is None:
                lang = getattr(self.app, 'current_lang_name', 'en')
            if lang == 'zh' and self._name_zh:
                return self._name_zh
            if lang == 'en' and self._name_en:
                return self._name_en
            return self._name_raw or 'Unnamed'

        def _ensure_loaded(self):
            """Import plugin module and resolve class if not already loaded."""
            if self._cls is not None and self._pkg_dir is not None:
                # Hot-reload: re-import if any source file changed since load.
                # load() skips mtime updates for alive plugins, so changes made
                # while running are picked up here after stop().
                if self._mgr._pkg_src_mtime(self._pkg_dir) != self._src_mtime:
                    self._cls = None
            if self._cls is not None:
                return True
            cls = self._mgr._import_class(
                self._pkg_dir, self._module_name, self._class_name)
            if cls is None:
                self._last_error = '模块导入失败'
                self._mgr.logger.warning(
                    f'Plugin {self._module_name} could not be loaded')
                return False
            self._cls = cls
            self._src_mtime = self._mgr._pkg_src_mtime(self._pkg_dir)
            # Sync metadata from loaded class (overrides AST-parsed values)
            self._name_raw = cls.name
            self._name_zh = getattr(cls, 'name_zh', None)
            self._name_en = getattr(cls, 'name_en', None)
            self._namespace = getattr(cls, 'namespace', None) or self._namespace
            self.priority = cls.priority
            if issubclass(cls, GuiPlugin):
                self.reload = cls.reload
                self.fixed_position = cls.fixed_position
                self.fixed_size = cls.fixed_size
                self.use_app_icon = cls.use_app_icon
            else:
                self.reload = True
            return True

        def start(self, parent, hidden=False):
            if not self._ensure_loaded():
                return None

            is_service = issubclass(self._cls, ServicePlugin)
            name = self.get_name()

            # ---- already running ----
            if self.alive:
                if is_service:
                    return None  # already running, use Stop to shut down
                else:
                    was_hidden = not self._inst.winfo_viewable()
                    self._inst.deiconify()
                    self._inst.lift()
                    self._inst.focus_force()
                    if was_hidden or not self._shown:
                        self._shown = True
                        self.app.emit('hook:will-show', HookInfo.from_handle(self), ns=NS)
                        try:
                            self._start(self._inst)
                        except Exception as e:
                            self._mgr.logger.error(
                                f'[Plugin:{name}] on_show error: {e}')
                        self.app.emit('hook:did-show', HookInfo.from_handle(self), ns=NS)
                    return self._inst

            # ---- stale instance (GUI only — ServicePlugin always auto-restarts) ----
            if not is_service and self.reload and self._inst is not None:
                try:
                    self.stop()
                except Exception:
                    pass
                self._inst = None

            # ---- create new instance ----
            is_hidden = not is_service and (hidden or (self.auto_start and self.start_hidden))
            try:
                NamespaceManager.check(self.namespace)
                namespaced_app = self.app.module(self.namespace)
                if is_service:
                    self._inst = self._cls(app=namespaced_app)
                else:
                    # 窗口构造即隐藏 (AppToplevel 接管防闪烁), 由
                    # _apply_window_setup 定位后显示; hidden/start_hidden
                    # 启动时构造前设类属性 _hidden_launch 阻止自动显示
                    # (构造时决定, 无事后取消的时序问题), finally 恢复
                    if is_hidden:
                        self._cls._hidden_launch = True
                    try:
                        self._inst = self._cls(parent, namespaced_app)
                    finally:
                        if is_hidden:
                            self._cls._hidden_launch = False
                NamespaceManager.add(self.namespace)
            except Exception as e:
                self._last_error = str(e)
                self._mgr.logger.error(
                    f'[Plugin:{name}] init error: {e}')
                return None
            if is_hidden:
                # self._inst.withdraw()
                self._shown = False
                if self.auto_start and self.start_hidden:
                    self.start_hidden = False  # only on first auto-start
            else:
                self._shown = True
                if is_service:
                    self.app.emit('hook:will-start', HookInfo.from_handle(self), ns=NS)
                else:
                    self.app.emit('hook:will-show', HookInfo.from_handle(self), ns=NS)
                try:
                    self._start(self._inst)
                except Exception as e:
                    action = 'on_start' if is_service else 'on_show'
                    self._mgr.logger.error(
                        f'[Plugin:{name}] {action} error: {e}')
                    if is_service:
                        return None  # did-start only emitted on success
                if is_service:
                    self.app.emit('hook:did-start', HookInfo.from_handle(self), ns=NS)
                else:
                    self.app.emit('hook:did-show', HookInfo.from_handle(self), ns=NS)

            # ---- window close protocol (GUI only) ----
            if not is_service:
                handle = self
                if self.reload:
                    def _on_close():
                        handle.close()
                    self._inst.protocol('WM_DELETE_WINDOW', _on_close)
                else:
                    def _on_close():
                        if handle._inst is not None:
                            handle.app.emit('hook:will-hide', HookInfo.from_handle(handle), ns=NS)
                            try:
                                handle._inst.on_hide()
                            except Exception as e:
                                handle._mgr.logger.error(
                                    f'[Plugin:{handle.get_name()}] on_hide error: {e}')
                            handle.app.emit('hook:did-hide', HookInfo.from_handle(handle), ns=NS)
                            try:
                                handle._inst.withdraw()
                            except Exception:
                                pass
                    self._inst.protocol('WM_DELETE_WINDOW', _on_close)

            return None if is_service else self._inst

    # ---- manager methods ---------------------------------------------------

    def __init__(self, logger, app):
        self.logger = logger
        self.plugins = {}
        self._ctrl_app = app
        self._plugin_path = getattr(app, 'plugin_path', None)
        self._setup_control_events()

    # -- public lifecycle API ----------------------------------------------
    #
    #   These are the single source of truth for plugin start/stop/show/hide.
    #   Both the menu and the control-event handlers route through here.

    def start_plugin(self, handle, parent, hidden=False):
        """Start *handle* and apply position + icon. Returns the window
        instance (GUI) or ``None`` (Service / already running).

        :rtype: object | None
        """
        was_loaded = handle.loaded

        if not handle.alive:
            win = handle.start(parent, hidden=hidden)
            if not handle.is_service:
                self._apply_window_setup(handle)
        elif not handle.is_service and not hidden:
            handle.show()
            win = handle._inst
        else:
            win = None

        menu_changed = handle.loaded and not was_loaded
        return win, menu_changed

    def stop_plugin(self, handle):
        """Stop (destroy) *handle*.

        Third-party plugins are fully unloaded (class + module dropped) so
        their memory is released; built-in plugins keep the class for a fast
        restart."""
        if handle.alive:
            handle.close()

    def show_plugin(self, handle):
        """Show a hidden GUI plugin window (no-op for services)."""
        if handle.alive and not handle.is_service:
            handle.show()

    def hide_plugin(self, handle):
        """Hide a visible GUI plugin window (no-op for services)."""
        if handle.alive and not handle.is_service:
            handle.hide()

    def get_plugin_info(self, target=None, refresh=False):
        """Return plugin status info as a dict.

        *target*: namespace / registry key → single dict; ``None`` → dict of dicts keyed by namespace.
        *refresh*: if True, re-scan plugin directories before querying.
        """
        if refresh:
            self.load(self._plugin_path)
        if target is not None:
            h = self._resolve_one(target)
            if h is None:
                return None
            return self._info_for(h[1])

        return {h.namespace: self._info_for(h) for h in self.plugins.values()}

    def _info_for(self, h):
        """Build an info dict for *handle*."""
        if h._cls:
            class_name = h._cls.__name__
        else:
            class_name = h._class_name or 'Unknown'
        return {
            'namespace':  h.namespace,
            'name':       h.get_name(),
            'type':       'ServicePlugin' if h.is_service else 'GuiPlugin',
            'alive':      h.alive,
            'visible':    h.visible,
            'class_name': class_name,
            'reload':     h.reload if not h.is_service else None,
        }

    def _apply_window_setup(self, handle):
        """Apply position and icon to a newly started GUI plugin window."""
        if handle.is_service:
            return
        win = handle._inst
        if win is None or not win.winfo_exists():
            return
        app = self._ctrl_app

        # position & size
        if handle.fixed_position or handle.fixed_size:
            app.emit('window:set-geometry', win,
                     x=(app.winfo_x() + app.winfo_width() + 4
                        if handle.fixed_position else None),
                     y=(app.winfo_y() if handle.fixed_position else None),
                     w=(420 if handle.fixed_size else None),
                     h=(app.main_height if handle.fixed_size else None),
                     fixed_size=handle.fixed_size,
                     fixed_position=handle.fixed_position)

        # # icon, AppToplevel接管了
        # if handle.use_app_icon:
        #     app.emit('window:set-icon', win)

        # Show the window now that it's positioned (was withdrawn during creation)
        if handle._shown and win.winfo_exists():
            win.deiconify()

    # -- control events ---------------------------------------------------

    def _setup_control_events(self):
        """Register lifecycle control events and services."""
        app = self._ctrl_app
        app.on('start',       self._on_plugin_start, ns=NS)
        app.on('stop',        self._on_plugin_stop,  ns=NS)
        app.on('show',        self._on_plugin_show,  ns=NS)
        app.on('hide',        self._on_plugin_hide,  ns=NS)
        app.on('auto-start',  self._on_auto_start,   ns=NS)

        app.services.register('get_info', self.get_plugin_info, ns=NS)
        app.services.register('check', self.check_plugin, ns=NS)
        self.register_agent_tools()

    def check_plugin(self, ns, timeout=None):
        """
        检测插件状态(如果不存在会重新扫描一遍)
        
        :params ns: 插件命名空间
        :param timeout: 如果指定了timeout, 当插件存在且不在线时, 就等待插件在线的超时时间
        :return
            -1: 不存在
            0: 存在但不在线
            1: 在线
        """
        if not ns:
            return -1
        if NamespaceManager.is_reserved(ns):
            return 1
        h = self._resolve_one(ns)
        if h is None:
            self.load(self._plugin_path)
            h = self._resolve_one(ns)
        if h is not None and timeout is not None and isinstance(timeout, (int, float)) and timeout > 0:
            expired = time.monotonic() + timeout
            while time.monotonic() < expired:
                if h[1].alive:
                    return 1
                time.sleep(0.01)
        return -1 if h is None else 1 if h[1].alive else 0

    def _resolve_one(self, target):
        """Look up a single target by namespace or registry key. Returns (key, Handle) or None."""
        for key, h in self.plugins.items():
            if h.namespace == target or key == target:
                return key, h
        return None

    def _resolve_targets(self, targets, exclude=None):
        """Resolve *targets* to a flat list of (key, Handle) pairs.

        *targets* may be a single namespace string, a list of strings,
        or ``'*'`` for all registered plugins.  *exclude* (namespace) is
        removed from the result — used to skip the caller on wildcard
        stop/hide.
        """
        if targets == '*':
            pairs = list(self.plugins.items())
        elif isinstance(targets, str):
            found = self._resolve_one(targets)
            pairs = [found] if found else []
        else:
            pairs = []
            for t in targets:
                found = self._resolve_one(t)
                if found:
                    pairs.append(found)
                else:
                    self.logger.warning('[PluginManager] unknown target: %s', t)
        if exclude:
            if isinstance(exclude, str):
                exclude = {exclude}
            else:
                exclude = set(exclude)
            pairs = [(k, h) for k, h in pairs if h.namespace not in exclude]
        return pairs

    def _on_plugin_start(self, targets, hidden=False, exclude=None):
        for _, h in self._resolve_targets(targets, exclude=exclude):
            self.start_plugin(h, self._ctrl_app, hidden=hidden)

    def _on_plugin_stop(self, targets, exclude=None):
        for _, h in self._resolve_targets(targets, exclude=exclude):
            self.stop_plugin(h)

    def _on_plugin_show(self, targets, exclude=None):
        for _, h in self._resolve_targets(targets, exclude=exclude):
            self.show_plugin(h)

    def _on_plugin_hide(self, targets, exclude=None):
        for _, h in self._resolve_targets(targets, exclude=exclude):
            self.hide_plugin(h)

    def _on_auto_start(self):
        """Load plugins then auto-start those whose ``auto_start`` flag is set."""
        self._ctrl_app.off('auto-start', self._on_auto_start, ns=NS)
        self.load(self._plugin_path)
        for h in self.plugins.values():
            if h.auto_start and not h.alive:
                self.start_plugin(h, self._ctrl_app)
        self._start_builtin_services()

    def _start_builtin_services(self):
        """Start built-in services that are not exported via __init__.py.

        These services are invisible in the plugin menu and always run
        in the background.  Each entry is a (import_path, class_name, namespace) tuple.
        """
        BUILTIN_SERVICES = [
            ('plugins.ai_assistant.agent_service', 'AgentService', 'agent'),
            ('plugins.task_scheduler.task_service', 'TasksService', 'tasks'),
            ('plugins.task_scheduler.notify_service', 'NotifyService', 'notify'),
        ]
        self._builtin_instances = getattr(self, '_builtin_instances', [])
        for import_path, class_name, namespace in BUILTIN_SERVICES:
            try:
                mod = __import__(import_path, fromlist=[class_name])
                cls = getattr(mod, class_name)
                svc = cls(app=self._ctrl_app.module(namespace))
                svc.on_start()
                NamespaceManager.add(namespace, True)
                self._builtin_instances.append(svc)
                self.logger.info('[PluginManager] built-in service started: %s', class_name)
            except Exception as e:
                self.logger.error(
                    '[PluginManager] failed to start built-in service %s: %s',
                    class_name, e)

    # -- AST-based metadata extraction (no import needed) --

    @staticmethod
    def _parse_metadata(pkg_dir):
        """Extract plugin metadata from source without executing it.

        Returns (module_name, class_name, metadata_dict) or (None, None, {}).
        """
        init_file = os.path.join(pkg_dir, '__init__.py')
        if not os.path.isfile(init_file):
            return None, None, {}

        try:
            with open(init_file, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
        except Exception:
            return None, None, {}

        # Find the import:  from .module import ClassName
        module_name = None
        class_name = None
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                # level > 0 means relative import (from .xxx / from ..xxx)
                if node.level > 0 and node.module and not node.module.startswith('_'):
                    module_name = node.module
                    for alias in node.names:
                        n = alias.name
                        if n and not n.startswith('_'):
                            class_name = n
                            break
            if module_name and class_name:
                break

        if not module_name or not class_name:
            return None, None, {}

        # Parse the module file to extract class-level attribute assignments
        module_file = os.path.join(pkg_dir, f'{module_name}.py')
        if not os.path.isfile(module_file):
            return None, None, {}

        try:
            with open(module_file, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())
        except Exception:
            return None, None, {}

        metadata = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    # Plain assign (targets list) or annotated assign (single
                    # target, e.g. `name: str = 'xx'`)
                    if isinstance(item, ast.Assign):
                        targets = item.targets
                    elif isinstance(item, ast.AnnAssign):
                        targets = [item.target] if item.target is not None else []
                    else:
                        continue
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id in PluginManager.META_KEYS:
                            if isinstance(item.value, ast.Constant):
                                metadata[target.id] = item.value.value
                        elif isinstance(target, ast.Name) and target.id == 'agent_tools':
                            # 能力声明: agent_tools = {纯字面量 dict} —
                            # 坏声明跳过, 不影响插件加载
                            try:
                                metadata['agent_tools'] = ast.literal_eval(item.value)
                            except Exception:
                                pass
        return module_name, class_name, metadata

    # -- Lazy import helper --

    @staticmethod
    def _pkg_src_mtime(pkg_dir):
        """Latest mtime of any .py file under *pkg_dir* (recursive).

        Used for change detection across the whole plugin package — editing a
        helper submodule (e.g. _cron_utils.py) is treated like editing the
        main module.
        """
        latest = 0.0
        for root, _dirs, files in os.walk(pkg_dir):
            for f in files:
                if f.endswith('.py'):
                    try:
                        m = os.path.getmtime(os.path.join(root, f))
                    except OSError:
                        continue
                    if m > latest:
                        latest = m
        return latest

    @staticmethod
    def _clear_module_cache(module_name):
        """Remove a plugin module and its submodules from sys.modules."""
        prefix = f'plugins.{module_name}'
        for key in list(sys.modules):
            if key == prefix or key.startswith(prefix + '.'):
                del sys.modules[key]

    def _import_class(self, pkg_dir, module_name, class_name):
        """Import a plugin module and return its GuiPlugin subclass, or None."""
        init_file = os.path.join(pkg_dir, '__init__.py')
        if not os.path.isfile(init_file):
            return None

        prefix = f'plugins.{module_name}'
        # Clear stale modules
        self._clear_module_cache(module_name)

        try:
            spec = importlib.util.spec_from_file_location(
                prefix, init_file,
                submodule_search_locations=[pkg_dir])
            if spec is None or spec.loader is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[prefix] = mod
            if pkg_dir not in sys.path:
                sys.path.insert(0, pkg_dir)
            spec.loader.exec_module(mod)

            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and (
                    (issubclass(obj, GuiPlugin) and obj is not GuiPlugin)
                    or (issubclass(obj, ServicePlugin) and obj is not ServicePlugin)):
                    return obj
        except Exception as e:
            self.logger.error(f'Failed to load plugin {module_name}: {e}')
        return None

    # -- main entry point --

    def load(self, path=None):
        """Discover and register plugins from plugin directories."""
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        plugin_dirs = [os.path.join(base, 'plugins')]   # built-in (always exists)
        if path:
            plugin_dirs.append(path)                    # third-party (absolute)
        # plugin_dirs[0] is always the built-in directory; plugin_dirs[1] is
        # third-party. Only third-party handles get their modules dropped
        # from sys.modules on unload.
        builtin_dir = plugin_dirs[0]
        # Ensure the third-party dir exists so users can drop plugins in
        # without creating it manually (a fresh empty dir is skipped by
        # iter_modules).
        if len(plugin_dirs) > 1 and plugin_dirs[1]:
            try:
                os.makedirs(plugin_dirs[1], exist_ok=True)
            except OSError:
                pass
        on_disk = set()
        for plugin_dir in plugin_dirs:
            if not plugin_dir or not os.path.isdir(plugin_dir):
                continue
            is_builtin = (plugin_dir == builtin_dir)
            for _finder, name, ispkg in pkgutil.iter_modules([plugin_dir]):
                if not ispkg or name.startswith('_'):
                    continue
                on_disk.add(name)

                # If already loaded and alive, skip
                if name in self.plugins:
                    h = self.plugins[name]
                    if h.alive:
                        continue

                pkg_dir = os.path.join(plugin_dir, name)

                # Already registered — skip unless the source has changed.
                # Source changes are detected here (mtime) but NOT re-imported:
                # the module is only (re)imported when the plugin is actually
                # started, via _ensure_loaded. Menu clicks stay cheap.
                if name in self.plugins:
                    h = self.plugins[name]
                    cur_mtime = self._pkg_src_mtime(pkg_dir)
                    if cur_mtime == h._src_mtime:
                        continue  # unchanged, skip re-parse
                    h._src_mtime = cur_mtime
                    if h._cls is not None:
                        h._cls = None  # re-import on next start(), not now
                    mod_name, cls_name, meta = self._parse_metadata(pkg_dir)
                    if mod_name and cls_name:
                        h._name_raw = meta.get('name') or mod_name or 'Unnamed'
                        h._name_zh = meta.get('name_zh')
                        h._name_en = meta.get('name_en')
                        h.priority = meta.get('priority', 0)
                    continue

                mod_name, cls_name, meta = self._parse_metadata(pkg_dir)
                if not mod_name:
                    continue

                h = self.Handle(
                    None, self._ctrl_app, self, pkg_dir=pkg_dir, module_name=mod_name,
                    class_name=cls_name, metadata=meta, key=name, builtin=is_builtin)
                # Record source mtime for change detection on subsequent scans
                h._src_mtime = self._pkg_src_mtime(pkg_dir)
                self.plugins[name] = h

        # Remove plugins that disappeared from disk
        for stale in list(self.plugins.keys() - on_disk):
            h = self.plugins[stale]
            if h.alive and not isinstance(h._inst, ServicePlugin) and h._inst.winfo_viewable():
                continue
            h.unload()
            del self.plugins[stale]

        # ---- validate namespace uniqueness ---------------
        ns_seen = {}
        ns_used = set([])
        for key, h in self.plugins.items():
            ns = h.namespace
            if h.alive:
                ns_used.add(ns)
            if ns in ns_seen:
                self.logger.error(
                    '[PluginManager] duplicate namespace "%s": '
                    'used by both "%s" and "%s"',
                    ns, ns_seen[ns], key)
            else:
                ns_seen[ns] = key
        NamespaceManager.update(ns_used)

    # -- Agent ---------------------------------------------------------

    def register_agent_tools(self):
        if self._ctrl_app:
            # 注册 agent 工具
            # 惰性 import — 保持模块 standalone (无 app 时不引入项目依赖)。
            from plugins.ai_assistant.core.registry import registry as agent_registry
            self._ctrl_app.services.register('list_capabilities', self._svc_list_capabilities, ns=NS)
            agent_registry.register('plugins_operation', fn=self.agent_plugins)

    def agent_plugins(self,
        action: Literal['start', 'stop', 'hide', 'list'],
        targets: str = '',
        exclude: str = '',
        hidden: bool = False,
        refresh: bool = False):
        """
        管理 UF Toolbox 插件: 启动/停止/隐藏应用内功能窗口, 或列出插件信息 (启动外部exe程序用 tools_operation)

        action: start=打开插件(未启动则启动, 已启动则前置显示); stop=停止销毁; hide=隐藏窗口(不销毁); list=列出插件信息(含namespace)
        targets: 目标插件namespace或显示名(中英文,支持模糊), 多个用;分隔, '*'=全部; list时省略=全部
        exclude: 要排除的插件(格式同targets), 仅配合'*'使用
        hidden: 仅start: False=显示窗口(默认; 已启动的会前置显示), True=静默(未启动=静默启动不弹窗, 已启动=隐藏窗口)
        refresh: 仅list: True=先重扫插件目录, 默认False
        """
        # agent 工具在 agent 工作线程执行, 而 start/stop/show/hide 都会
        # 触碰 Tk (构造/销毁/显隐窗口) — tkinter 非线程安全, 且工作线程
        # 构造窗口会与主线程的 after(0) 自动显示竞争 (窗口先在默认位置
        # 亮相再被重新定位, 表现为闪烁), 故整体切主线程执行
        return self._run_on_ui(lambda: self._agent_plugins_impl(
            action, targets, exclude, hidden, refresh))

    def _run_on_ui(self, fn, timeout=15):
        """在主线程执行 fn 并回传返回值 (agent 工作线程 → 主线程).

        主线程调用时直接执行; 否则 after(0) 调度 + Event 阻塞等待
        (同 agent_service._confirm 的握手模式), 超时按失败返回.
        """
        if threading.current_thread() is threading.main_thread():
            return fn()
        box = {}
        done = threading.Event()

        def _wrap():
            try:
                box['v'] = fn()
            except Exception as e:
                box['e'] = e
            finally:
                done.set()

        try:
            self._ctrl_app.after(0, _wrap)
        except Exception as e:
            return 'error: %s' % e
        if not done.wait(timeout):
            return 'error: 主线程执行超时'
        if 'e' in box:
            return 'error: %s' % box['e']
        return box.get('v')

    def _agent_plugins_impl(self, action, targets, exclude, hidden,
                            refresh):
        """agent_plugins 的实际逻辑 (主线程执行, 见 agent_plugins)."""
        if action == 'list':
            if not targets.strip():
                return self.get_plugin_info(refresh=refresh)
            handles, err = self._agent_targets(targets)
            ret = {h.namespace: self._info_for(h) for _, h in handles}
            if err:
                ret['_errors'] = err
            return ret
        handles, err = self._agent_targets(targets)
        if not handles:
            return err or 'error: targets is required'
        if exclude.strip():
            excluded = set()
            for token in exclude.split(';'):
                hit, _cands = self._agent_resolve(token)
                if hit:
                    excluded.add(hit[1].namespace)
            handles = [(k, h) for k, h in handles
                       if h.namespace not in excluded]
        if not handles:
            return 'error: targets 全部被 exclude 排除'
        # 结果按执行后真实状态判定 (start_plugin 对服务恒返回 None,
        # 不能据返回值判成败); 统一返回 {namespace: 'ok'|'failed[: 原因]'}
        if action == 'start':
            ret = {}
            for _, h in handles:
                h._last_error = None
                if h.alive and hidden and not h.is_service:
                    # 已启动 + 静默指令 → 隐藏窗口 (hide 的逆操作也走 start,
                    # 模型只需记 start/hide 两个动作)
                    self.hide_plugin(h)
                    ret[h.namespace] = 'ok' if not h.visible else 'failed'
                    continue
                self.start_plugin(h, self._ctrl_app, hidden=hidden)
                if h.alive:
                    ret[h.namespace] = 'ok'
                else:
                    # 带回失败原因 (init error 等) — 模型可据此判断是
                    # 重试还是放弃, 而不是对着干巴巴的 failed 瞎试
                    err2 = h._last_error
                    ret[h.namespace] = ('failed: %s' % err2) if err2 else 'failed'
        else:
            op, check = {
                'stop': (self.stop_plugin, lambda h: not h.alive),
                'hide': (self.hide_plugin, lambda h: not h.visible),
            }.get(action, (None, None))
            if op is None:
                return 'error: unknown action %r' % action
            ret = {}
            for _, h in handles:
                op(h)
                ret[h.namespace] = 'ok' if check(h) else 'failed'
        if err:
            # 部分目标未匹配: 附在结果里 (不阻塞已匹配目标的执行),
            # 模型拿到明确事实, 不会对未执行目标幻觉成功
            ret['_errors'] = err
        return ret

    def _agent_targets(self, targets):
        """解析 agent 传入的分号分隔目标串.

        返回 (handles, error_str|None) — 部分目标解析失败不阻塞其余
        目标, 失败信息 (含候选清单与工具指引) 由 error_str 返回,
        调用方并入结果 (结果的 _errors 键)。
        """
        resolved, errs = self._resolve_agent_tokens(targets)
        if errs:
            # 兜底重扫一次: 插件目录可能刚放入新插件。重扫仅毫秒级
            # (目录遍历 + mtime 比对, 仅新插件才 AST 解析), 比失败后
            # 让模型二次调用省一整轮 LLM 往返
            try:
                self.load(self._plugin_path)
            except Exception:
                pass
            resolved, errs = self._resolve_agent_tokens(targets)
        if not errs:
            return resolved, None
        lines = []
        for token, cands in errs:
            if cands:
                opts = '; '.join('%s(%s)' % (h.get_name(), h.namespace)
                                 for _, h in cands)
                lines.append('%r 匹配到多个候选: %s' % (token, opts))
            else:
                lines.append('%r 未匹配到插件' % token)
        avail = '; '.join('%s(%s)' % (h.get_name(), h.namespace)
                          for h in self.plugins.values())
        # 错误尾部互相指引 — 模型首次选错工具时第二轮必中
        return None, ('error: %s. 可用插件: %s. 如果你要启动的是外部程序'
                      '(终端/exe等), 请改用 tools_operation'
                      % (' | '.join(lines), avail))

    def _resolve_agent_tokens(self, targets):
        """逐 token 解析目标串 → (resolved pairs, [(token, 候选), ...])."""
        resolved, errs = [], []
        for token in targets.split(';'):
            token = token.strip()
            if not token:
                continue
            if token == '*':
                resolved.extend(self.plugins.items())
                continue
            hit, cands = self._agent_resolve(token)
            if hit:
                resolved.append(hit)
            else:
                errs.append((token, cands))
        return resolved, errs

    def _agent_resolve(self, token):
        """单个目标解析: namespace 精确 → 显示名(中/英)精确 → 唯一包含匹配.

        返回 ((key, Handle) | None, 候选 list); 候选仅在歧义/模糊
        多中时非空, 供错误提示使用.
        """
        token = token.strip()
        if not token:
            return None, []
        hit = self._resolve_one(token)
        if hit:
            return hit, []
        tl = token.lower()

        def names(h):
            return {n.lower() for n in
                    (h._name_raw, h._name_zh, h._name_en) if n}

        pairs = list(self.plugins.items())
        exact = [p for p in pairs if tl in names(p[1])]
        if len(exact) == 1:
            return exact[0], []
        if exact:
            return None, exact
        fuzzy = [p for p in pairs
                 if any(tl in n or n in tl for n in names(p[1]))]
        if len(fuzzy) == 1:
            return fuzzy[0], []
        return None, fuzzy

    def _svc_list_capabilities(self):
        """全部已发现插件的 agent 能力声明 (含未启动插件, 不执行插件代码)."""
        caps = []
        for key, h in self.plugins.items():
            tools = h._agent_tools
            if isinstance(tools, dict) and tools:
                caps.append({'plugin': h.namespace or key, 'tools': tools})
        return caps

