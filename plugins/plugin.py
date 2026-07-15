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

    The app reference is available as self.app.
    """

    name = "Unnamed Plugin"
    use_app_icon = True
    fixed_position = True
    fixed_size = True
    reload = True
    priority = 0

    def __init__(self, parent=None, app=None):
        self.app = app
        super().__init__(parent)

    def on_show(self):
        """Called when the window becomes visible — first open or reopened after hide."""
        print(f'[plugin] on_show: {self.name}')

    def on_hide(self):
        """Called when the window is hidden (reload=False only) — user closed → withdrawn."""
        print(f'[plugin] on_hide: {self.name}')

    def on_destroy(self):
        """Called before the instance is destroyed — final cleanup.

        Override to release resources: cancel timers, close connections,
        unregister event listeners (self.app.off(...)), join threads, etc.
        """
        print(f'[plugin] on_destroy: {self.name}')
