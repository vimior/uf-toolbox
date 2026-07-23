# -*- coding: utf-8 -*-
"""Shared state store — namespaced, observable key-value storage."""
import logging
import time

_SELF = object()  # sentinel: "show my own"


class Store:
    """Global key-value store with change notifications via the event bus.

    Designed to be accessed as ``app.store``.  Each plugin creates a
    namespaced handle via ``module(name)`` so writes are scoped.
    """

    def __init__(self, eventbus, perf=None, logger=None):
        self._eventbus = eventbus
        self._perf = perf  # PerfMonitor instance (optional)
        self._logger = logger or logging.getLogger(__name__)
        self._state = {}          # key → value
        self._owners = {}         # key → owner (last writer)
        self._subscriptions = {}  # owner → [(event_key, callback), ...]
        self._meta = {}           # key → {commit_count, last_commit}

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
        if self._perf and self._perf.enabled and owner:
            self._perf.record_store_commit(owner)
        meta = self._meta.get(key)
        if meta is None:
            self._meta[key] = {'commit_count': 1, 'last_commit': time.time()}
        else:
            meta['commit_count'] += 1
            meta['last_commit'] = time.time()
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
            if self._perf and self._perf.enabled:
                self._perf.record_store_subscribe(owner)

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
        for k in [k for k, v in self._owners.items() if v == owner]:
            self._state.pop(k, None)
            self._owners.pop(k, None)
            self._meta.pop(k, None)
            # Don't clear listeners — other plugins may still listen to this
            # key and expect callbacks when the key is re-committed later.

    # ---- snapshot ----

    def snapshot(self):
        """Return a point-in-time snapshot of all stored keys.

        Returns a dict::

            {'keys': [{'key': str, 'value': str, 'owner': str,
                       'commit_count': int, 'last_commit': float|None,
                       'subscribers': [str, ...]}, ...]}
        """
        keys = []
        for key, value in self._state.items():
            owner = self._owners.get(key, '-')
            meta = self._meta.get(key, {})
            subs = []
            event = f'store:changed:{key}'
            for sub_owner, pairs in self._subscriptions.items():
                for ev, cb in pairs:
                    if ev == event:
                        subs.append(sub_owner)
            keys.append({
                'key': key,
                'value': str(value)[:80],
                'owner': owner,
                'commit_count': meta.get('commit_count', 0),
                'last_commit': meta.get('last_commit'),
                'subscribers': subs,
            })
        return {'keys': keys}


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

    def dump(self):
        """Return a dict of all key-value pairs owned by this module."""
        return {k: self.get(k, raw=True) for k in self._store.keys(owner=self._name)}
