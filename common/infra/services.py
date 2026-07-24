# -*- coding: utf-8 -*-
"""Service registry — register/call/unregister for cross-plugin method calls.

Plugins register named functions; other plugins look them up and invoke
them synchronously (blocking until the call returns).
"""
import time
import logging


_SELF = object()  # sentinel: "show my own"


class Services:
    """Named function directory with discovery notifications.

    Designed to be accessed as ``app.services``.  Plugins can register
    callables under a dotted name (``plugin.func`` by convention) and
    other plugins call them with ``app.services.call(name, ...)``.
    """

    def __init__(self, eventbus, perf=None, logger=None):
        self._eventbus = eventbus
        self._perf = perf  # PerfMonitor instance (optional)
        self._logger = logger or logging.getLogger(__name__)
        self._services = {}       # name → fn
        self._owners = {}         # name → owner (who registered)
        self._subscriptions = {}  # owner → [(event, callback), ...]
        self._meta = {}      # name → {call_count, last_call}
        self._callers = {}   # name → {caller_ns → {count, last_call}}

    # ---- public API ----

    def register(self, name, fn, owner=''):
        """Register *fn* under *name*.  Emits ``service:registered``."""
        self._services[name] = fn
        if owner:
            self._owners[name] = owner
        self._meta.setdefault(name, {})['since'] = time.time()
        self._logger.info('[services] register %s', name)
        self._eventbus.emit('service:registered', name)

    def call(self, name, *args, **kwargs):
        """Invoke the service *name* and return its result.

        Raises ``KeyError`` if not registered.
        """
        origin = kwargs.pop('_origin', None)
        fn = self._services.get(name)
        if fn is None:
            raise KeyError(f'Service not registered: {name}')
        meta = self._meta.setdefault(name, {})
        meta['call_count'] = meta.get('call_count', 0) + 1
        meta['last_call'] = time.time()
        meta.setdefault('since', time.time())
        if origin:
            self._callers.setdefault(name, {}).setdefault(origin, {'count': 0})
            self._callers[name][origin]['count'] += 1
            self._callers[name][origin]['last_call'] = time.time()
        tag = name + (f' (from {origin})' if origin else '')
        self._logger.debug('[services] call %s', tag)
        perf = self._perf
        if perf and perf.enabled:
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed = time.perf_counter() - t0
            owner = self._owners.get(name, 'unknown')
            perf.record_service(owner, name, elapsed)
            return result
        return fn(*args, **kwargs)

    def unregister(self, name):
        """Remove *name* from the registry.  Emits ``service:unregistered``."""
        fn = self._services.pop(name, None)
        self._owners.pop(name, None)
        self._meta.pop(name, None)
        self._callers.pop(name, None)
        if fn:
            self._logger.info('[services] unregister %s', name)
        self._eventbus.emit('service:unregistered', name)

    def has(self, name):
        return name in self._services

    def keys(self, owner=None):
        """Return registered service names, optionally filtered by *owner*."""
        if owner is None:
            return list(self._services.keys())
        return [k for k, v in self._owners.items() if v == owner]

    def module(self, name):
        """Return a namespaced handle for *name* (auto-prefixes on register)."""
        return _ServiceModule(self, name)

    # ---- discovery (subscription-tracked) --------------------------

    def on_registered(self, callback, owner=''):
        """Listen for ``service:registered`` events."""
        event = 'service:registered'
        self._eventbus.on(event, callback)
        if owner:
            self._subscriptions.setdefault(owner, []).append((event, callback))

    def on_unregistered(self, callback, owner=''):
        """Listen for ``service:unregistered`` events."""
        event = 'service:unregistered'
        self._eventbus.on(event, callback)
        if owner:
            self._subscriptions.setdefault(owner, []).append((event, callback))

    # ---- cleanup ---------------------------------------------------

    def cleanup(self, owner):
        """Remove all traces of *owner* (called on plugin destroy)."""
        for event, callback in self._subscriptions.pop(owner, []):
            self._eventbus.off(event, callback)
        for name in self.keys(owner=owner):
            self.unregister(name)

    # ---- snapshot ----

    def snapshot(self):
        """Return a point-in-time snapshot of all registered services.

        Returns a dict::

            {'services': [{'name': str, 'owner': str,
                           'call_count': int, 'last_call': float|None}, ...]}
        """
        services = []
        for name in self._services:
            meta = self._meta.get(name, {})
            callers = []
            for ns, cd in self._callers.get(name, {}).items():
                callers.append({'namespace': ns, 'count': cd['count'],
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
    """Namespaced handle for a specific plugin — auto-prefixes on register."""

    def __init__(self, services, name):
        self._services = services
        self._name = name

    def register(self, key, fn):
        """Register *fn* as ``self._name.key``."""
        self._services.register(f'{self._name}.{key}', fn, owner=self._name)

    def call(self, name, *args, **kwargs):
        """Invoke a service by full name (no prefixing)."""
        kwargs.pop('_origin', None)
        return self._services.call(name, *args, _origin=self._name, **kwargs)

    def unregister(self, key):
        """Remove ``self._name.key`` from the registry."""
        self._services.unregister(f'{self._name}.{key}')

    def has(self, key):
        return self._services.has(f'{self._name}.{key}')

    def keys(self, owner=_SELF):
        """Return service names, filtered by *owner*.  Defaults to this
        plugin's own registered services."""
        if owner is _SELF:
            owner = self._name
        return self._services.keys(owner=owner)

    def on_registered(self, callback, owner=''):
        self._services.on_registered(callback, owner)

    def on_unregistered(self, callback, owner=''):
        self._services.on_unregistered(callback, owner)
