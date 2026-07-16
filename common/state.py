# -*- coding: utf-8 -*-
"""Shared state with observer pattern."""
import json
import locale
import os
import tkinter as tk
from tkinter import ttk

from themes import DARK_THEME, LIGHT_THEME
from i18n import ZH, EN
from common.eventbus import EventBus
from common.store import Store
from common.services import Services

_CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.uf_toolbox.json')


class AppState:
    """Cross-component shared state. Writes use set_xxx() methods."""

    # ---- event bus / store / services -------------------------------

    @property
    def eventbus(self):
        return self._eventbus

    @property
    def store(self):
        return self._store

    @property
    def services(self):
        return self._services

    # ---- event bus delegates ----------------------------------------

    def on(self, event, callback):
        self._eventbus.on(event, callback)

    def off(self, event, callback):
        self._eventbus.off(event, callback)

    def clear(self, event):
        self._eventbus.clear(event)

    def emit(self, event, *args, **kwargs):
        self._eventbus.emit(event, *args, **kwargs)

    # ---- lifecycle hooks -------------------------------------------
    #
    #   hook:plugin:will-show   hook:plugin:did-show
    #   hook:plugin:will-hide   hook:plugin:did-hide
    #   hook:plugin:will-destroy  hook:plugin:did-destroy
    #
    # AppState listens for did-destroy to release store/services.

    def init(self):
        """Override in subclasses to register event listeners."""
        self._eventbus.on('hook:plugin:did-destroy', self._on_plugin_destroyed)
        try:
            super().init()
        except AttributeError:
            pass

    def _on_plugin_destroyed(self, plugin):
        """Clean up store/services when a plugin instance is destroyed."""
        ns = getattr(type(plugin), 'namespace', None) or type(plugin).__name__
        self._store.cleanup(ns)
        self._services.cleanup(ns)

    def init_state(self):
        """Initialize all state. Called once from main.py.__init__."""
        self._eventbus = EventBus()
        self._store = Store(self._eventbus)
        self._services = Services(self._eventbus)

        self._listeners = {}
        self._config = self._load_config()
        theme_name = self._config.get('theme', 'dark')
        lang_name = self._config.get('lang', 'auto')
        self._current_theme_name = theme_name
        self._current_lang_name = lang_name
        self._theme = DARK_THEME if theme_name == 'dark' else LIGHT_THEME
        self._lang = (ZH if lang_name == 'zh' else EN
                      if lang_name == 'en' else self._resolve_lang())
        self._main_width = 520
        self._main_height = 44
        base = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        self._ico_path = os.path.join(base, 'icons', 'uf_toolbox.ico')
        self._png_path = os.path.join(base, 'icons', 'uf_toolbox.png')
        self._ttk_style = ttk.Style()
        try:
            self._ttk_style.theme_use('clam')
        except tk.TclError:
            pass

    # ---- properties ----

    @property
    def theme(self):
        return self._theme

    @property
    def lang(self):
        return self._lang

    @property
    def current_theme_name(self):
        return self._current_theme_name

    @property
    def current_lang_name(self):
        return self._current_lang_name

    @property
    def ico_path(self):
        return self._ico_path

    @property
    def png_path(self):
        return self._png_path

    @property
    def main_width(self):
        return self._main_width

    def set_main_width(self, v):
        self._main_width = v

    @property
    def main_height(self):
        return self._main_height

    def set_main_height(self, v):
        self._main_height = v

    @property
    def resolved_lang(self):
        """Return 'zh' or 'en', resolving 'auto' to system locale."""
        name = self._current_lang_name
        if name == 'auto':
            try:
                loc = locale.getdefaultlocale()[0]
                return 'zh' if (loc and loc.startswith('zh')) else 'en'
            except Exception:
                return 'en'
        return name or 'en'

    @property
    def config(self):
        return self._config

    @property
    def tool_path(self):
        return self._config.get('tool_path', 'tools')

    @property
    def plugin_path(self):
        return self._config.get('plugin_path', 'plugins')

    @property
    def ttk_style(self):
        return self._ttk_style

    @property
    def always_on_top(self):
        return self._config.get('topmost', False)

    def set_topmost(self, value):
        self._config['topmost'] = bool(value)
        self._save_config()

    @property
    def auto_hide_enabled(self):
        return self._config.get('auto_hide', True)

    def set_auto_hide(self, value):
        self._config['auto_hide'] = bool(value)
        self._save_config()

    # ---- theme / lang ----

    def set_theme(self, name=None):
        if name is not None:
            self._theme = DARK_THEME if name == 'dark' else LIGHT_THEME
            self._current_theme_name = name
            self._config['theme'] = name
            self._save_config()

    def set_lang(self, name=None):
        if name is not None:
            self._lang = (self._resolve_lang() if name == 'auto'
                          else ZH if name == 'zh' else EN)
            self._current_lang_name = name
            self._config['lang'] = name
            self._save_config()

    @staticmethod
    def _resolve_lang():
        try:
            loc = locale.getdefaultlocale()[0]
            return ZH if loc and loc.startswith('zh') else EN
        except Exception:
            return EN

    def _load_config(self):
        try:
            if os.path.exists(_CONFIG_PATH):
                with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {'theme': 'dark', 'lang': 'auto', 'topmost': False, 'auto_hide': True}

    def _save_config(self):
        try:
            with open(_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f)
        except Exception:
            pass
