# -*- coding: utf-8 -*-
"""Shared state store — namespaced, observable key-value storage."""
import logging
import time
from .utils import _namespace_of, _resolve_name

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
        self._owners = {}         # key → owner
        self._meta = {}           # key → {commit_count, last_commit}

    # ---- public API ----

    def module(self, ns):
        """Return a namespaced handle for *ns* (usually a plugin namespace)."""
        return _StoreModule(self, ns)

    def commit(self, key, value, ns):
        """Set *key* to *value* and notify subscribers.

        Cross-namespace writes are rejected: a plugin whose *ns* differs
        from the ``@`` prefix in *key* may not commit to that key.
        """
        key = _resolve_name(key, ns)
        key_owner = _namespace_of(key)
        if key_owner != ns:
            self._logger.warning(
                '[store] %s → %s namespace rejected: %s', ns, key_owner, key)
            return
        old = self._state.get(key)
        self._state[key] = value
        self._owners[key] = ns
        if self._perf and self._perf.enabled:
            self._perf.record_store_commit(ns)
        meta = self._meta.get(key)
        if meta is None:
            self._meta[key] = {'commit_count': 1, 'last_commit': time.time()}
        else:
            meta['commit_count'] += 1
            meta['last_commit'] = time.time()
        self._logger.debug('[store] commit %s => %s (from %s)', key, value, ns)
        self._eventbus.emit(f'store:changed:{key}', value, old, ns=ns)

    def get(self, key, default=None, ns=None):
        if ns:
            key = _resolve_name(key, ns)
        return self._state.get(key, default)

    def keys(self, ns=None):
        """Return all keys, optionally filtered by namespace."""
        if ns is None:
            return list(self._state.keys())
        return [k for k, v in self._owners.items() if v == ns]

    def subscribe(self, key, callback, ns):
        """Register *callback* to be called when *key* changes."""
        key = _resolve_name(key, ns)
        event = f'store:changed:{key}'
        self._eventbus.on(event, callback, ns=ns)
        if self._perf and self._perf.enabled:
            self._perf.record_store_subscribe(ns)

    def unsubscribe(self, key, callback, ns):
        """Remove subscriptions for *key*."""
        key = _resolve_name(key, ns)
        event = f'store:changed:{key}'
        if callback:
            self._eventbus.off(event, callback, ns=ns)
        else:
            self._eventbus.clear(event, ns=ns)

    # ---- cleanup ----

    def cleanup(self, ns):
        """Remove all traces of a namespace (called on plugin destroy).

        Callback cleanup is handled by EventBus.cleanup(ns).
        Only data owned by *ns* is removed here.
        """
        for k in [k for k, v in self._owners.items() if v == ns]:
            self._state.pop(k, None)
            self._owners.pop(k, None)
            self._meta.pop(k, None)

    # ---- snapshot ----

    def snapshot(self, ns=None):
        """Return a point-in-time snapshot of all stored keys.

        If *ns* is given, only keys owned by or prefixed with
        that namespace are returned.

        Returns::

            {
                'keys': [
                    {
                        'key':           str,
                        'value':         str,
                        'owner':         str,
                        'commit_count':  int,
                        'last_commit':   float | None,
                    },
                ],
            }
        """
        keys = []
        for key, value in self._state.items():
            meta = self._meta.get(key, {})
            keys.append({
                'key': key,
                'value': str(value)[:80],
                'owner': self._owners.get(key, '-'),
                'commit_count': meta.get('commit_count', 0),
                'last_commit': meta.get('last_commit'),
            })
        if ns:
            prefix = ns + '@'
            keys = [k for k in keys if k['key'].startswith(prefix)
                    or k['owner'] == ns]
        return {'keys': keys}


class _StoreModule:
    """Namespaced store handle — ns is auto-injected, key prefixing is
    handled by :class:`Store` via :func:`_resolve_name`.
    """

    __slots__ = ('_store', '_ns')

    def __init__(self, store, ns):
        self._store = store
        self._ns = ns

    def commit(self, key, value):
        self._store.commit(key, value, ns=self._ns)

    def get(self, key, default=None):
        return self._store.get(key, default, ns=self._ns)

    def subscribe(self, key, callback):
        self._store.subscribe(key, callback, ns=self._ns)

    def unsubscribe(self, key, callback=None):
        self._store.unsubscribe(key, callback, ns=self._ns)

    def keys(self, ns=_SELF):
        """Return keys, filtered by namespace.  Defaults to this module's own."""
        ns = self._ns if ns is _SELF else ns
        return self._store.keys(ns=ns)

    def cleanup(self):
        self._store.cleanup(self._ns)

    def snapshot(self):
        return self._store.snapshot(ns=self._ns)

    def dump(self):
        """Return a dict of all key-value pairs owned by this module."""
        return {k: self._store.get(k) for k in self._store.keys(ns=self._ns)}
