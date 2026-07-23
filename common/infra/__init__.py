# -*- coding: utf-8 -*-
"""Infrastructure layer — eventbus, store, services wired together."""
import logging

from .eventbus import EventBus
from .store import Store
from .services import Services
from .perf import PerfMonitor


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

    def emit(self, event, *args, **kwargs):
        self._infra.eventbus.emit(event, *args, _origin=self._ns, **kwargs)

    def __getattr__(self, name):
        try:
            return getattr(self._infra, name)
        except AttributeError:
            if self._app is not None:
                return getattr(self._app, name)
            raise


class Infrastructure:
    """Manages the three shared runtime components.

    Provides ``on/off/emit/clear`` delegates to EventBus, ``module(ns)``
    for namespaced plugin handles, and ``cleanup(ns)`` for teardown.
    """

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self.perf = PerfMonitor(logger=self._logger)
        self.eventbus = EventBus(perf=self.perf, logger=self._logger)
        self.store = Store(self.eventbus, perf=self.perf, logger=self._logger)
        self.services = Services(self.eventbus, perf=self.perf, logger=self._logger)

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
