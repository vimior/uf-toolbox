# -*- coding: utf-8 -*-
"""Base class for plugins — standalone, no external dependencies."""
import os
import sys
import pkgutil
import importlib.util
import tkinter as tk
from common.common import get_logger

logger = get_logger()


class PluginBase:
    """Base class all plugins must inherit from.

    Subclasses MUST set:
        name: str — display name shown in the menu
    Subclasses MAY override:
        on_load(self) — called once after the plugin is loaded
        create_window(self, parent) — create and return a tk.Toplevel, or None

    The app reference is available as self._app.
    """

    name = "Unnamed Plugin"
    use_app_icon = True
    fixed_position = True
    fixed_size = True
    reload = True
    priority = 0

    def __init__(self, app=None):
        self._app = app
        super().__init__()

    def create_window(self, parent):
        """Create the plugin window. Return the Toplevel or None."""
        return None

    def on_load(self):
        """Called after instantiation. When reload=False this runs only once."""
        pass


class PluginHandle:
    """Lazy handle — defers instantiation until create_window() is called."""

    __slots__ = ('name', 'fixed_position', 'fixed_size', 'use_app_icon',
                 'reload', 'priority', '_cls', '_app', '_inst', '_win')

    def __init__(self, cls, app):
        self.name = cls.name
        self.fixed_position = cls.fixed_position
        self.fixed_size = cls.fixed_size
        self.use_app_icon = cls.use_app_icon
        self.reload = cls.reload
        self.priority = cls.priority
        self._cls = cls
        self._app = app
        self._inst = None
        self._win = None

    @property
    def alive(self):
        return self._win is not None and self._win.winfo_exists()

    def create_window(self, parent):
        if self.alive:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
            return self._win

        if self.reload:
            self._inst = None

        if self._inst is None:
            self._inst = self._cls(self._app)
            self._inst.on_load()
        self._win = self._inst.create_window(parent)
        if self._win is None and isinstance(self._inst, tk.Toplevel):
            self._win = self._inst

        if not self.reload:
            self._win.protocol('WM_DELETE_WINDOW', self._win.withdraw)
        return self._win


def load_plugins(app, plugins, plugin_dirs):
    """Scan *plugin_dirs* for plugin packages."""

    on_disk = set()
    for plugin_dir in plugin_dirs:
        if not os.path.isdir(plugin_dir):
            continue
        for _finder, name, ispkg in pkgutil.iter_modules([plugin_dir]):
            if not ispkg or name.startswith('_'):
                continue
            on_disk.add(name)
            if name in plugins:
                h = plugins[name]
                if h.alive:
                    continue

            prefix = f'plugins.{name}'
            for key in list(sys.modules):
                if key == prefix or key.startswith(prefix + '.'):
                    del sys.modules[key]

            try:
                pkg_dir = os.path.join(plugin_dir, name)
                init_file = os.path.join(pkg_dir, '__init__.py')
                if not os.path.isfile(init_file):
                    continue
                spec = importlib.util.spec_from_file_location(
                    f'plugins.{name}', init_file,
                    submodule_search_locations=[pkg_dir])
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[f'plugins.{name}'] = mod
                if pkg_dir not in sys.path:
                    sys.path.insert(0, pkg_dir)
                spec.loader.exec_module(mod)

                cls = None
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if (isinstance(obj, type)
                            and issubclass(obj, PluginBase)
                            and obj is not PluginBase):
                        cls = obj
                        break
                if cls is None:
                    logger.warning(
                        f'Plugin {name} has no PluginBase subclass — skipped')
                    continue

                if hasattr(cls, 'name_zh'):
                    lang = getattr(app, 'current_lang_name', 'en')
                    cls.name = cls.name_zh if lang == 'zh' else cls.name_en

                existed = name in plugins
                if existed:
                    h = plugins[name]
                    if h.alive:
                        h._win.destroy()
                plugins[name] = PluginHandle(cls, app)
                logger.info(
                    f'Plugin {"reloaded" if existed else "discovered"}: '
                    f'{cls.name} ({name})')
            except Exception as e:
                plugins.pop(name, None)
                logger.error(f'Failed to load plugin {name}: {e}')

    for stale in list(plugins.keys() - on_disk):
        h = plugins[stale]
        if h.alive and h._win.winfo_viewable():
            continue
        del plugins[stale]
        logger.info(f'Plugin removed: {stale}')
