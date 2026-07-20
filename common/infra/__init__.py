# -*- coding: utf-8 -*-
"""Infrastructure layer — eventbus, store, services wired together."""

from .eventbus import EventBus
from .store import Store
from .services import Services


class _Module:
    """Namespaced handle returned by ``Infrastructure.module(ns)``.

    ``eventbus``, ``store`` and ``services`` are all pre-namespaced;
    ``on()`` / ``off()`` are convenience delegates to the namespaced eventbus.
    Everything else passes through to the parent Infrastructure first,
    then falls back to *app* (AppState) for theme / lang / config etc.
    """

    __slots__ = ('_infra', '_app', '_ns', 'eventbus', 'store', 'services')

    def __init__(self, infra, ns, app=None):
        self._infra = infra
        self._app = app
        self._ns = ns
        self.eventbus = infra.eventbus.module(ns)
        self.store = infra.store.module(ns)
        self.services = infra.services.module(ns)

    def on(self, event, callback):
        self.eventbus.on(event, callback)

    def off(self, event, callback):
        self.eventbus.off(event, callback)

    def __getattr__(self, name):
        try:
            return getattr(self._infra, name)
        except AttributeError:
            return getattr(self._app, name)


class Infrastructure:
    """Manages the three shared runtime components.

    Provides ``on/off/emit/clear`` delegates to EventBus, ``module(ns)``
    for namespaced plugin handles, and ``cleanup(ns)`` for teardown.
    """

    def __init__(self):
        self.eventbus = EventBus()
        self.store = Store(self.eventbus)
        self.services = Services(self.eventbus)

    def module(self, name, app=None):
        """Return a namespaced handle — store, services, eventbus all scoped.
        *app* (AppState) is used as a fallback for __getattr__."""
        return _Module(self, name, app)

    # ---- eventbus delegates ----

    def on(self, event, callback):
        self.eventbus.on(event, callback)

    def off(self, event, callback):
        self.eventbus.off(event, callback)

    def clear(self, event):
        self.eventbus.clear(event)

    def emit(self, event, *args, **kwargs):
        self.eventbus.emit(event, *args, **kwargs)

    # ---- plugin lifecycle ----

    def cleanup(self, ns):
        """Remove all traces of namespace *ns* from all three subsystems."""
        self.eventbus.cleanup(ns)
        self.store.cleanup(ns)
        self.services.cleanup(ns)
