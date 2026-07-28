# -*- coding: utf-8 -*-
"""Service registry — register/call/unregister for cross-plugin method calls.

Plugins register named functions; other plugins look them up and invoke
them synchronously (blocking until the call returns).
"""
import time
import logging
from .utils import _namespace_of, _resolve_name


_SELF = object()  # sentinel: "show my own"


class Services:
    """Named function directory with discovery notifications.

    Designed to be accessed as ``app.services``.  Plugins can register
    callables under a namespaced name (``plugin@func``) and
    other plugins call them with ``app.services.call(name, ...)``.
    """

    def __init__(self, eventbus, perf=None, logger=None):
        self._eventbus = eventbus
        self._perf = perf  # PerfMonitor instance (optional)
        self._logger = logger or logging.getLogger(__name__)
        self._services = {}       # name → fn
        self._owners = {}         # name → owner (who registered)
        self._meta = {}           # name → {call_count, last_call}
        self._callers = {}        # name → {caller_ns → {count, last_call}}

    # ---- public API ----

    def register(self, name, fn, ns):
        """Register *fn* under *name*.  Emits ``services@registered``.

        *ns* is the owner for cleanup / filtering.
        """
        name = _resolve_name(name, ns)
        self._owners[name] = ns
        self._services[name] = fn
        self._meta.setdefault(name, {})['since'] = time.time()
        self._logger.info('[services] register %s', name)
        self._eventbus.emit('services@registered', name, ns=ns)

    def call(self, name, *args, ns, **kwargs):
        """Invoke the service *name* and return its result.

        *kwargs* are forwarded to the service function.
        Raises ``KeyError`` if not registered.
        """
        name = _resolve_name(name, ns)
        fn = self._services.get(name)
        if fn is None:
            raise KeyError(f'Service not registered: {name}')
        meta = self._meta.setdefault(name, {})
        meta['call_count'] = meta.get('call_count', 0) + 1
        meta['last_call'] = time.time()
        meta.setdefault('since', time.time())
        self._callers.setdefault(name, {}).setdefault(ns, {'count': 0})
        self._callers[name][ns]['count'] += 1
        self._callers[name][ns]['last_call'] = time.time()
        self._logger.debug('[services] call %s (from %s)', name, ns)
        perf = self._perf
        if perf and perf.enabled:
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed = time.perf_counter() - t0
            perf.record_service(ns, name, elapsed)
            return result
        return fn(*args, **kwargs)

    def unregister(self, name, ns):
        """Remove *name* from the registry.  Emits ``services@unregistered``.

        Cross-namespace removal is rejected (same convention as :meth:`Store.commit`).
        """
        name = _resolve_name(name, ns)
        key_ns = _namespace_of(name)
        if key_ns != ns:
            self._logger.warning(
                '[services] %s → %s namespace rejected for unregister: %s',
                ns, key_ns, name)
            return
        fn = self._services.pop(name, None)
        self._owners.pop(name, None)
        self._meta.pop(name, None)
        self._callers.pop(name, None)
        if fn:
            self._logger.info('[services] unregister %s', name)
        self._eventbus.emit('services@unregistered', name, ns=ns)

    def has(self, name, ns=None):
        if ns:
            name = _resolve_name(name, ns)
        return name in self._services

    def names(self, ns=None):
        """Return registered service names, optionally filtered by namespace."""
        if ns is None:
            return list(self._services.keys())
        return [k for k, v in self._owners.items() if v == ns]

    def module(self, ns):
        """Return a namespaced handle for *ns* (auto-prefixes on register)."""
        return _ServiceModule(self, ns)

    # ---- discovery (subscription-tracked) --------------------------

    def on_registered(self, callback, ns):
        """Listen for ``services@registered`` events."""
        self._eventbus.on('services@registered', callback, ns=ns)

    def off_registered(self, callback, ns):
        """Stop listening for ``services@registered`` events."""
        self._eventbus.off('services@registered', callback, ns=ns)

    def on_unregistered(self, callback, ns):
        """Listen for ``services@unregistered`` events."""
        self._eventbus.on('services@unregistered', callback, ns=ns)

    def off_unregistered(self, callback, ns):
        """Stop listening for ``services@unregistered`` events."""
        self._eventbus.off('services@unregistered', callback, ns=ns)

    # ---- cleanup ---------------------------------------------------

    def cleanup(self, ns):
        """Remove all traces of a namespace (called on plugin destroy).

        Callback cleanup is handled by EventBus.cleanup(ns).
        Only registered services owned by *ns* are removed here.
        """
        for name in self.names(ns=ns):
            self.unregister(name, ns=ns)

    # ---- snapshot ----

    def snapshot(self, ns=None):
        """Return a point-in-time snapshot of registered services.

        If *ns* is given, only services owned by that namespace are returned.

        Returns::

            {
                'services': [
                    {
                        'name':        str,
                        'owner':       str,
                        'call_count':  int,
                        'last_call':   float | None,
                        'since':       float,
                        'callers': [
                            {
                                'namespace':  str,
                                'count':      int,
                                'last_call':  float,
                            },
                        ],
                    },
                ],
            }
        """
        services = []
        for name in self._services:
            if ns and self._owners.get(name) != ns:
                continue
            meta = self._meta.get(name, {})
            callers = []
            for caller_ns, cd in self._callers.get(name, {}).items():
                callers.append({'namespace': caller_ns, 'count': cd['count'],
                                'last_call': cd.get('last_call')})
            callers.sort(key=lambda c: c['count'], reverse=True)
            services.append({
                'name': name,
                'owner': self._owners.get(name, '-'),
                'call_count': meta.get('call_count', 0),
                'last_call': meta.get('last_call'),
                'since': meta.get('since'),
                'callers': callers,
            })
        return {'services': services}


class _ServiceModule:
    """Namespaced handle — ns is auto-injected, name prefixing is
    handled by :class:`Services` via :func:`_resolve_name`.
    """

    __slots__ = ('_services', '_ns')

    def __init__(self, services, ns):
        self._services = services
        self._ns = ns

    def register(self, name, fn):
        self._services.register(name, fn, ns=self._ns)

    def call(self, name, *args, **kwargs):
        kwargs.pop('ns', None)
        return self._services.call(name, *args, ns=self._ns, **kwargs)

    def unregister(self, name):
        self._services.unregister(name, ns=self._ns)

    def has(self, name):
        return self._services.has(name, ns=self._ns)

    def names(self, ns=_SELF):
        ns = self._ns if ns is _SELF else ns
        return self._services.names(ns=ns)

    def cleanup(self):
        self._services.cleanup(self._ns)

    def snapshot(self):
        return self._services.snapshot(ns=self._ns)

    def on_registered(self, callback):
        self._services.on_registered(callback, ns=self._ns)

    def off_registered(self, callback):
        self._services.off_registered(callback, ns=self._ns)

    def on_unregistered(self, callback):
        self._services.on_unregistered(callback, ns=self._ns)

    def off_unregistered(self, callback):
        self._services.off_unregistered(callback, ns=self._ns)
