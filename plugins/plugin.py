# -*- coding: utf-8 -*-
"""Plugin base class."""
import tkinter as tk
from dataclasses import dataclass


class GuiPlugin(tk.Toplevel):
    """GUI plugin base class — the plugin instance IS its window.

    Inherit from this for plugins that open a window.
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
    namespace = None
    use_app_icon = True
    fixed_position = True
    fixed_size = True
    reload = True
    priority = 0
    auto_start = False
    start_hidden = False

    def __init__(self, parent=None, app=None):
        self.app = app
        self.store = self.app.store
        self.services = self.app.services
        super().__init__(parent)

    def on_show(self):
        """Called when the window becomes visible — first open or reopened after hide."""
        pass

    def on_hide(self):
        """Called when the window is hidden (reload=False only) — user closed → withdrawn."""
        pass

    def on_destroy(self):
        """Called before the instance is destroyed — final cleanup."""
        pass


# Backward-compatible alias
PluginBase = GuiPlugin


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
    namespace = None
    priority = 0
    auto_start = False

    def __init__(self, app=None):
        self.app = app
        self.root = app._app  # the root Tk window (for popups, toasts, etc.)
        self.store = self.app.store
        self.services = self.app.services

    def on_start(self):
        """Called when the service starts — first start or restart."""
        pass

    def on_stop(self):
        """Called before shutdown — final cleanup."""
        pass


@dataclass(frozen=True, slots=True)
class HookInfo:
    """Read-only lifecycle hook snapshot — 通知而非授权.

    Passed to hook listeners so they know *what* happened without
    gaining control over other plugins' lifecycle or internals.
    """

    namespace: str
    name: str
    is_service: bool
    alive: bool
    visible: bool

    @classmethod
    def from_handle(cls, handle):
        return cls(
            namespace=handle.namespace,
            name=handle.get_name(),
            is_service=handle.is_service,
            alive=handle.alive,
            visible=handle.visible,
        )
