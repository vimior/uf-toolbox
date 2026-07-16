# -*- coding: utf-8 -*-
"""Service registry — register/call/unregister for cross-plugin method calls.

Plugins register named functions; other plugins look them up and invoke
them synchronously (blocking until the call returns).
"""

_SELF = object()  # sentinel: "show my own"


class Services:
    """Named function directory with discovery notifications.

    Designed to be accessed as ``app.services``.  Plugins can register
    callables under a dotted name (``plugin.func`` by convention) and
    other plugins call them with ``app.services.call(name, ...)``.
    """

    def __init__(self, eventbus):
        self._eventbus = eventbus
        self._services = {}       # name → fn
        self._owners = {}         # name → owner (who registered)
        self._subscriptions = {}  # owner → [(event, callback), ...]

    # ---- public API ----

    def register(self, name, fn, owner=''):
        """Register *fn* under *name*.  Emits ``service:registered``."""
        self._services[name] = fn
        if owner:
            self._owners[name] = owner
        print(f'[services] register {name}')
        self._eventbus.emit('service:registered', name)

    def call(self, name, *args, **kwargs):
        """Invoke the service *name* and return its result.

        Raises ``KeyError`` if not registered.
        """
        fn = self._services.get(name)
        if fn is None:
            raise KeyError(f'Service not registered: {name}')
        return fn(*args, **kwargs)

    def unregister(self, name):
        """Remove *name* from the registry.  Emits ``service:unregistered``."""
        fn = self._services.pop(name, None)
        self._owners.pop(name, None)
        if fn:
            print(f'[services] unregister {name}')
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
        return self._services.call(name, *args, **kwargs)

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

    on_registered = Services.on_registered
    on_unregistered = Services.on_unregistered
