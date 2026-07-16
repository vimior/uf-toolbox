# -*- coding: utf-8 -*-
"""Shared state store — namespaced, observable key-value storage."""

_SELF = object()  # sentinel: "show my own"


class Store:
    """Global key-value store with change notifications via the event bus.

    Designed to be accessed as ``app.store``.  Each plugin creates a
    namespaced handle via ``module(name)`` so writes are scoped.
    """

    def __init__(self, eventbus):
        self._eventbus = eventbus
        self._state = {}          # key → value
        self._owners = {}         # key → owner (last writer)
        self._subscriptions = {}  # owner → [(event_key, callback), ...]

    # ---- public API ----

    def module(self, name):
        """Return a namespaced handle for *name* (usually a plugin name).

        All keys written through the handle are prefixed ``name.`` so
        plugins don't step on each other's data.
        """
        return _StoreModule(self, name)

    def commit(self, key, value, owner=''):
        """Set *key* to *value* and notify subscribers."""
        old = self._state.get(key)
        self._state[key] = value
        if owner:
            self._owners[key] = owner
        self._eventbus.emit(f'store:changed:{key}', value, old)

    def get(self, key, default=None):
        return self._state.get(key, default)

    def keys(self, owner=None):
        """Return all keys, optionally filtered by *owner*."""
        if owner is None:
            return list(self._state.keys())
        return [k for k, v in self._owners.items() if v == owner]

    def subscribe(self, key, callback, owner=''):
        """Register *callback* to be called when *key* changes."""
        event = f'store:changed:{key}'
        self._eventbus.on(event, callback)
        if owner:
            self._subscriptions.setdefault(owner, []).append((event, callback))

    def unsubscribe(self, key, callback=None):
        """Remove subscriptions for *key*."""
        event = f'store:changed:{key}'
        if callback:
            self._eventbus.off(event, callback)
        else:
            self._eventbus.clear(event)

    # ---- cleanup ----

    def cleanup(self, owner):
        """Remove all traces of *owner* (called on plugin destroy).

        Subscription cleanup is unconditional — a plugin that subscribed
        to someone else's key still gets cleaned up.  Data cleanup only
        happens for keys this owner last wrote.
        """
        for event, callback in self._subscriptions.pop(owner, []):
            self._eventbus.off(event, callback)
        keys = [k for k, v in self._owners.items() if v == owner]
        for k in keys:
            self._state.pop(k, None)
            self._owners.pop(k, None)
            self._eventbus.clear(f'store:changed:{k}')


class _StoreModule:
    """Namespaced store handle bound to a specific owner."""

    def __init__(self, store, name):
        self._store = store
        self._name = name

    def _key(self, key, *, raw=False):
        """Prefix *key* with the module name unless *raw* is True."""
        return key if raw else f'{self._name}.{key}'

    def commit(self, key, value, *, raw=False):
        """Set *key*.  Auto-prefixed unless ``raw=True``."""
        self._store.commit(self._key(key, raw=raw), value, owner=self._name)

    def get(self, key, default=None, *, raw=False):
        return self._store.get(self._key(key, raw=raw), default)

    def subscribe(self, key, callback, *, raw=False):
        """Subscribe to changes on *key*.  Auto-prefixed unless ``raw=True``."""
        self._store.subscribe(self._key(key, raw=raw), callback, owner=self._name)

    def unsubscribe(self, key, callback=None, *, raw=False):
        self._store.unsubscribe(self._key(key, raw=raw), callback)

    def keys(self, owner=_SELF):
        """Return keys, filtered by *owner*.  Defaults to this module's own."""
        if owner is _SELF:
            owner = self._name
        return self._store.keys(owner=owner)

    def snapshot(self):
        """Return a dict of all key-value pairs owned by this module."""
        return {k: self.get(k, raw=True) for k in self._store.keys(owner=self._name)}
