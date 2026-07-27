# -*- coding: utf-8 -*-
"""Shared state with observer pattern."""
import json
import locale
import os
import tkinter as tk
from tkinter import ttk

from themes import DARK_THEME, LIGHT_THEME
from i18n import ZH, EN
from common.common import logger
from common.infra import Infrastructure

_CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.uf_toolbox.json')


class AppState:
    """Cross-component shared state. Writes use set_xxx() methods."""

    # ---- event bus / store / services -------------------------------

    @property
    def eventbus(self):
        return self._infra.eventbus

    @property
    def store(self):
        return self._infra.store

    @property
    def services(self):
        return self._infra.services

    def module(self, name):
        """Return a namespaced app handle for a plugin — same pattern as
        ``store.module(name)`` and ``services.module(name)``."""
        return self._infra.module(name, app=self)

    # ---- event bus delegates ----------------------------------------

    @staticmethod
    def _resolve_event(event, ns=None):
        """@ present → fully qualified, otherwise → ns@event (default ns=app)."""
        if '@' in event:
            return event
        return f'{ns or "app"}@{event}'

    def on(self, event, callback, ns=None):
        resolved = self._resolve_event(event, ns)
        self._infra.on(resolved, callback, ns=ns or 'app')

    def off(self, event, callback, ns=None):
        self._infra.off(self._resolve_event(event, ns), callback)

    def clear(self, event, ns=None):
        self._infra.clear(self._resolve_event(event, ns))

    def emit(self, event, *args, ns=None, **kwargs):
        kwargs.setdefault('ns', ns or 'app')
        self._infra.emit(self._resolve_event(event, ns), *args, **kwargs)

    # ---- lifecycle hooks -------------------------------------------
    #
    #   plugins@hook:will-start  plugins@hook:did-start   (ServicePlugin)
    #   plugins@hook:will-stop   plugins@hook:did-stop    (ServicePlugin)
    #   plugins@hook:will-show   plugins@hook:did-show    (GUI plugin)
    #   plugins@hook:will-hide   plugins@hook:did-hide    (GUI plugin)
    #   plugins@hook:will-destroy  plugins@hook:did-destroy  (GUI plugin)
    #
    # AppState listens for did-stop / did-destroy to release store/services.

    def init(self):
        """Override in subclasses to register event listeners."""
        self.on('plugins@hook:did-destroy', self._on_plugin_destroyed)
        self.on('plugins@hook:did-stop', self._on_plugin_destroyed)
        try:
            super().init()
        except AttributeError:
            pass

    def _on_plugin_destroyed(self, info, **kwargs):
        """Clean up store/services when a plugin is stopped/destroyed."""
        emit_ns = kwargs.get('ns', None)
        if not emit_ns or emit_ns != 'plugins' or not info:
            return
        self._infra.cleanup(info.namespace)

    def init_state(self):
        """Initialize all state. Called once from main.py.__init__."""
        self._infra = Infrastructure(logger=logger)

        self._config = self._load_config()
        theme_name = self._config.get('theme', 'dark')
        lang_name = self._config.get('lang', 'auto')
        self._current_theme_name = theme_name
        self._config_lang_name = lang_name   # raw config value: 'zh', 'en', 'auto', ...
        self._locale_lang_name = self._resolve_locale()  # always 'zh' or 'en'
        self._theme = DARK_THEME if theme_name == 'dark' else LIGHT_THEME
        self._lang = ZH if self.current_lang_name == 'zh' else EN
        self._main_width = 520
        self._main_height = 44
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    def config_lang_name(self):
        """Raw config value — 'zh', 'en', 'auto', etc. For UI that needs
        to distinguish explicit selection from auto-detection."""
        return self._config_lang_name

    @property
    def current_lang_name(self):
        """Effective language — always 'zh' or 'en'. Uses config value
        when set explicitly, otherwise falls back to system locale."""
        if self._config_lang_name in ('zh', 'en'):
            return self._config_lang_name
        return self._locale_lang_name

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
            self._config_lang_name = name    # update raw first
            self._lang = ZH if self.current_lang_name == 'zh' else EN
            self._config['lang'] = name
            self._save_config()

    @staticmethod
    def _resolve_locale():
        """Resolve system locale to 'zh' or 'en'."""
        try:
            loc = locale.getdefaultlocale()[0]
            return 'zh' if (loc and loc.startswith('zh')) else 'en'
        except Exception:
            return 'en'

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
