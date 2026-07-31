# -*- coding: utf-8 -*-
"""Plugin manager — discovery, lazy-loading, lifecycle, hot-reload."""
import ast
import os
import sys
import pkgutil
import importlib.util

from plugins.plugin import GuiPlugin, HookInfo, ServicePlugin

NS = 'plugins'


class NamespaceManager:
    _RESERVED = set(['app', NS, 'services'])
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
                     '_namespace')

        def __init__(self, cls, app, mgr, pkg_dir=None, module_name=None,
                     class_name=None, metadata=None, key=None):
            self.app = app
            self._mgr = mgr
            self._cls = cls
            self._inst = None
            self._pkg_dir = pkg_dir
            self._module_name = module_name
            self._class_name = class_name
            self._shown = False
            self._name_raw = None
            self._name_zh = None
            self._name_en = None
            self._src_mtime = 0
            self._key = key
            self._namespace = None

            if cls is not None:
                # Eager — class attributes are available directly
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
            if self._cls is not None:
                return True
            cls = self._mgr._import_class(
                self._pkg_dir, self._module_name, self._class_name)
            if cls is None:
                self._mgr.logger.warning(
                    f'Plugin {self._module_name} could not be loaded')
                return False
            self._cls = cls
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
            try:
                NamespaceManager.check(self.namespace)
                namespaced_app = self.app.module(self.namespace)
                if is_service:
                    self._inst = self._cls(app=namespaced_app)
                else:
                    self._inst = self._cls(parent, namespaced_app)
                    self._inst.withdraw()  # hide until positioned by _apply_window_setup
                NamespaceManager.add(self.namespace)
            except Exception as e:
                self._mgr.logger.error(
                    f'[Plugin:{name}] init error: {e}')
                return None
            is_hidden = not is_service and (hidden or (self.auto_start and self.start_hidden))
            if is_hidden:
                self._inst.withdraw()
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
                        handle.stop()
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
        """Stop (destroy) *handle*."""
        if handle.alive:
            handle.stop()

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
            self.load()
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

        # icon
        if handle.use_app_icon:
            app.emit('window:set-icon', win)

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
            ('plugins.task_scheduler.task_service', 'TasksService', 'tasks'),
            ('plugins.task_scheduler.notify_service', 'NotifyService', 'notify'),
        ]
        self._builtin_instances = getattr(self, '_builtin_instances', [])
        for import_path, class_name, namespace in BUILTIN_SERVICES:
            try:
                mod = __import__(import_path, fromlist=[class_name])
                cls = getattr(mod, class_name)
                svc = cls(app=self._ctrl_app.module(namespace))
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
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id in PluginManager.META_KEYS:
                                if isinstance(item.value, ast.Constant):
                                    metadata[target.id] = item.value.value
        return module_name, class_name, metadata

    # -- Lazy import helper --

    def _import_class(self, pkg_dir, module_name, class_name):
        """Import a plugin module and return its GuiPlugin subclass, or None."""
        init_file = os.path.join(pkg_dir, '__init__.py')
        if not os.path.isfile(init_file):
            return None

        prefix = f'plugins.{module_name}'
        # Clear stale modules
        for key in list(sys.modules):
            if key == prefix or key.startswith(prefix + '.'):
                del sys.modules[key]

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

    @staticmethod
    def _resolve_plugin_dirs(path=None):
        """Return a list of plugin directories to scan.

        *path* is the optional custom plugin path from app config.
        """
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs = [os.path.join(base, 'plugins')]

        exe_ext = os.path.splitext(sys.argv[0])[1].lower()
        if exe_ext not in ('.py', '.pyw'):
            # packaged
            exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
            p = os.path.join(exe_dir, 'plugins')
            if os.path.isdir(p) and p not in dirs:
                dirs.append(p)
                if exe_dir not in sys.path:
                    sys.path.insert(0, exe_dir)
            if path and path != 'plugins':
                p = os.path.join(exe_dir, path)
                if os.path.isdir(p) and p not in dirs:
                    dirs.append(p)
                    root = os.path.dirname(p)
                    if root not in sys.path:
                        sys.path.insert(0, root)
        else:
            # dev
            dirs.append(os.path.join(base, 'dist', 'plugins'))
            if path and path != 'plugins':
                p = os.path.join(base, 'dist', path)
                if os.path.isdir(p) and p not in dirs:
                    dirs.append(p)
        return dirs

    def load(self, path=None):
        """Discover and register plugins from plugin directories."""
        plugin_dirs = self._resolve_plugin_dirs(path)
        on_disk = set()
        for plugin_dir in plugin_dirs:
            if not os.path.isdir(plugin_dir):
                continue
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

                # If already loaded (but not alive), reload if module was imported
                if name in self.plugins and self.plugins[name]._cls is not None:
                    mod_name, cls_name, meta = self._parse_metadata(pkg_dir)
                    if not mod_name:
                        continue
                    cls = self._import_class(pkg_dir, mod_name, cls_name)
                    if cls is None:
                        continue
                    # Update the handle with new class, keep mutable state
                    old_h = self.plugins[name]
                    saved = old_h.start_hidden, old_h._shown
                    old_h.unload()
                    self.plugins[name] = self.Handle(
                        cls, self._ctrl_app, self, pkg_dir=pkg_dir, module_name=mod_name,
                        class_name=cls_name, key=name)
                    self.plugins[name].start_hidden, self.plugins[name]._shown = saved
                    continue

                # (Re)discover lazily — refresh metadata from source if changed
                if name in self.plugins:
                    h = self.plugins[name]
                    module_file = os.path.join(pkg_dir, f'{h._module_name}.py')
                    try:
                        cur_mtime = os.path.getmtime(module_file)
                    except OSError:
                        cur_mtime = 0
                    if cur_mtime == h._src_mtime:
                        continue  # unchanged, skip re-parse
                    h._src_mtime = cur_mtime
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
                    class_name=cls_name, metadata=meta, key=name)
                # Record source mtime for change detection on subsequent scans
                module_file = os.path.join(pkg_dir, f'{mod_name}.py')
                try:
                    h._src_mtime = os.path.getmtime(module_file)
                except OSError:
                    pass
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

