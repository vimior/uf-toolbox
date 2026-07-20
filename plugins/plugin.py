# -*- coding: utf-8 -*-
"""Plugin base class."""
import tkinter as tk


class PluginBase(tk.Toplevel):
    """Base class all plugins must inherit from.

    PluginBase is a tk.Toplevel — the plugin instance IS its window.
    Build your UI in __init__ using ``self`` as the parent.

    Subclasses MUST set:
        name: str — display name shown in the menu
    Subclasses MAY override:
        __init__(self, parent=None, app=None) — build UI here; call super().__init__(parent, app)
        on_show(self) — called when the window becomes visible (first open or reopen)
        on_hide(self) — called when the window is hidden (reload=False only, user closes → withdraw)
        on_destroy(self) — called before the instance is destroyed (final cleanup)

    self.app is a namespaced proxy — listeners registered via
    ``self.app.on()`` are auto-cleaned on destroy.
    """

    name = "Unnamed Plugin"
    use_app_icon = True
    fixed_position = True
    fixed_size = True
    reload = True
    priority = 0
    auto_start = False
    start_hidden = False

    def __init__(self, parent=None, app=None):
        ns = getattr(type(self), 'namespace', None) or type(self).__name__
        self.app = app.module(ns)
        self.store = self.app.store
        self.services = self.app.services
        super().__init__(parent)

    def on_show(self):
        """Called when the window becomes visible — first open or reopened after hide."""
        print(f'[plugin] on_show: {self.name}')

    def on_hide(self):
        """Called when the window is hidden (reload=False only) — user closed → withdrawn."""
        print(f'[plugin] on_hide: {self.name}')

    def on_destroy(self):
        """Called before the instance is destroyed — final cleanup."""
        print(f'[plugin] on_destroy: {self.name}')


class ServicePlugin:
    """Headless plugin — provides services without a window.

    Inherit from this if your plugin has no UI and only exists to register
    services that other plugins call via ``app.services.call(...)``.

    Subclasses MUST set:
        name: str — display name shown in the menu
    Subclasses MAY override:
        __init__(self, app=None) — register services here; call super().__init__(app)
        on_show(self) — called when the service starts (first start or restart)
        on_destroy(self) — called before shutdown (final cleanup)

    self.app is a namespaced proxy — listeners registered via
    ``self.app.on()`` are auto-cleaned on stop.
    """

    name = "Unnamed Service"
    priority = 0
    auto_start = False

    def __init__(self, app=None):
        ns = getattr(type(self), 'namespace', None) or type(self).__name__
        self.app = app.module(ns)
        self.store = self.app.store
        self.services = self.app.services

    def on_start(self):
        """Called when the service starts — first start or restart."""
        print(f'[plugin] on_start: {self.name}')

    def on_stop(self):
        """Called before shutdown — final cleanup."""
        print(f'[plugin] on_stop: {self.name}')
