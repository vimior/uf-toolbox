# -*- coding: utf-8 -*-
"""Plugin manager — discovery, lazy-loading, lifecycle, hot-reload."""
import ast
import os
import sys
import pkgutil
import importlib.util

from plugins.plugin import PluginBase, ServicePlugin


class PluginManager:
    """Manages plugin discovery, loading, lifecycle, and hot-reload.

    Usage::

        from common.common import logger
        pm = PluginManager(logger)
        pm.load(app, plugin_dirs)
        # pm.plugins is the {name: Handle} registry
    """

    META_KEYS = ('name', 'name_zh', 'name_en', 'priority', 'fixed_position',
                 'fixed_size', 'use_app_icon', 'reload', 'auto_start',
                 'start_hidden')

    # ---- inner handle class ------------------------------------------------

    class Handle:
        """Lazy handle — defers import + instantiation until start() is called.

        When *cls* is None (lazy mode), the plugin module is imported on first use.
        Otherwise it behaves eagerly (legacy / reload path)."""

        __slots__ = ('name', 'fixed_position', 'fixed_size', 'use_app_icon',
                     'reload', 'priority', 'auto_start', 'start_hidden',
                     '_cls', 'app', '_inst', '_pkg_dir', '_module_name',
                     '_class_name', '_mgr', '_shown')

        def __init__(self, cls, app, mgr, pkg_dir=None, module_name=None,
                     class_name=None, metadata=None):
            self.app = app
            self._mgr = mgr
            self._cls = cls
            self._inst = None
            self._pkg_dir = pkg_dir
            self._module_name = module_name
            self._class_name = class_name
            self._shown = False

            if cls is not None:
                # Eager — class attributes are available directly
                self.name = cls.name
                self.priority = cls.priority
                self.auto_start = getattr(cls, 'auto_start', False)
                self.start_hidden = getattr(cls, 'start_hidden', False)
                if issubclass(cls, PluginBase):
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
                raw_name = meta.get('name') or module_name or 'Unnamed'
                # Resolve i18n name: name_zh/name_en take priority over raw name
                name_zh = meta.get('name_zh')
                name_en = meta.get('name_en')
                if name_zh or name_en:
                    lang = getattr(app, 'current_lang_name', 'en')
                    raw_name = (name_zh if lang == 'zh' else name_en) or raw_name
                self.name = raw_name
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
                if is_service or self._inst.winfo_exists():
                    self.app.emit('hook:plugin:will-destroy', self._inst)
                    try:
                        self._stop(self._inst)
                    except Exception as e:
                        self._mgr.logger.error(
                            f'Plugin {self.name} on_destroy error: {e}')
                    self.app.emit('hook:plugin:did-destroy', self._inst)
                    if not is_service:
                        try:
                            self._inst.destroy()
                        except Exception:
                            pass
                self._inst = None
                self._shown = False
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
                if is_service or self._inst.winfo_exists():
                    self.app.emit('hook:plugin:will-destroy', self._inst)
                    try:
                        self._stop(self._inst)
                    except Exception as e:
                        self._mgr.logger.error(
                            f'[Plugin:{self.name}] on_destroy error: {e}')
                    self.app.emit('hook:plugin:did-destroy', self._inst)
                    if not is_service:
                        try:
                            self._inst.destroy()
                        except Exception:
                            pass
                self._inst = None
                self._shown = False

        def restart(self, parent):
            """Force destroy + recreate the plugin window (dev-time hot-reload)."""
            self.stop()
            return self.start(parent)

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
            # Update metadata from actual class (may differ from AST-parsed values,
            # e.g. dynamic name_zh/name_en resolution)
            if hasattr(cls, 'name_zh'):
                lang = getattr(self.app, 'current_lang_name', 'en')
                cls.name = cls.name_zh if lang == 'zh' else cls.name_en
            self.name = cls.name
            self.priority = cls.priority
            if issubclass(cls, PluginBase):
                self.reload = cls.reload
                self.fixed_position = cls.fixed_position
                self.fixed_size = cls.fixed_size
                self.use_app_icon = cls.use_app_icon
            else:
                self.reload = True
            return True

        def start(self, parent):
            if not self._ensure_loaded():
                return None

            is_service = issubclass(self._cls, ServicePlugin)

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
                        self.app.emit('hook:plugin:will-show', self._inst)
                        try:
                            self._start(self._inst)
                        except Exception as e:
                            self._mgr.logger.error(
                                f'[Plugin:{self.name}] on_show error: {e}')
                        self.app.emit('hook:plugin:did-show', self._inst)
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
                if is_service:
                    self._inst = self._cls(app=self.app)
                else:
                    self._inst = self._cls(parent, self.app)
            except Exception as e:
                self._mgr.logger.error(
                    f'[Plugin:{self.name}] init error: {e}')
                return None
            hidden = not is_service and self.auto_start and self.start_hidden
            if hidden:
                self._inst.withdraw()
                self._shown = False
                self.start_hidden = False  # only on first auto-start
            else:
                self._shown = True
                self.app.emit('hook:plugin:will-show', self._inst)
                try:
                    self._start(self._inst)
                except Exception as e:
                    self._mgr.logger.error(
                        f'[Plugin:{self.name}] on_show error: {e}')
                self.app.emit('hook:plugin:did-show', self._inst)

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
                            handle.app.emit('hook:plugin:will-hide', handle._inst)
                            try:
                                handle._inst.on_hide()
                            except Exception as e:
                                handle._mgr.logger.error(
                                    f'[Plugin:{handle.name}] on_hide error: {e}')
                            handle.app.emit('hook:plugin:did-hide', handle._inst)
                            try:
                                handle._inst.withdraw()
                            except Exception:
                                pass
                    self._inst.protocol('WM_DELETE_WINDOW', _on_close)

            return None if is_service else self._inst

    # ---- manager methods ---------------------------------------------------

    def __init__(self, logger):
        self.logger = logger
        self.plugins = {}

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
        """Import a plugin module and return its PluginBase subclass, or None."""
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
                    (issubclass(obj, PluginBase) and obj is not PluginBase)
                    or (issubclass(obj, ServicePlugin) and obj is not ServicePlugin)):
                    return obj
        except Exception as e:
            self.logger.error(f'Failed to load plugin {module_name}: {e}')
        return None

    # -- main entry point --

    def load(self, app, plugin_dirs):
        """Scan *plugin_dirs* for plugin packages, populating self.plugins.

        First call discovers plugins using AST parsing (no import).
        Actual module import is deferred until the user opens a plugin window.
        Subsequent calls refresh already-loaded and newly-appearing plugins.
        """

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
                        cls, app, self, pkg_dir=pkg_dir, module_name=mod_name,
                        class_name=cls_name)
                    self.plugins[name].start_hidden, self.plugins[name]._shown = saved
                    continue

                # First discovery — use AST to get metadata, defer import
                if name in self.plugins:
                    # Already discovered lazily, skip
                    continue

                mod_name, cls_name, meta = self._parse_metadata(pkg_dir)
                if not mod_name:
                    continue

                self.plugins[name] = self.Handle(
                    None, app, self, pkg_dir=pkg_dir, module_name=mod_name,
                    class_name=cls_name, metadata=meta)

        # Remove plugins that disappeared from disk
        for stale in list(self.plugins.keys() - on_disk):
            h = self.plugins[stale]
            if h.alive and not isinstance(h._inst, ServicePlugin) and h._inst.winfo_viewable():
                continue
            h.unload()
            del self.plugins[stale]
