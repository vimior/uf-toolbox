# -*- coding: utf-8 -*-
"""Lightweight pub-sub event bus."""
import time
import logging


class EventBus:
    """Publish-subscribe event system — on / off / emit / clear.

    Used by ``AppState`` as ``app.eventbus``; ``app.on()`` / ``app.emit()``
    delegate here for convenience.
    """

    def __init__(self, perf=None, logger=None):
        self._listeners = {}
        self._namespaced = {}  # ns → [(event, callback), ...]
        self._meta = {}  # event → {count, last_emit}
        self._cb_since = {}  # id(callback) → timestamp
        self._perf = perf  # PerfMonitor instance (optional)
        self._logger = logger or logging.getLogger(__name__)

    # ---- helpers ----

    @staticmethod
    def _name(cb):
        """Human-readable name for *cb*."""
        # bound method: ClassName.method
        if hasattr(cb, '__self__') and hasattr(cb, '__func__'):
            s = cb.__self__
            owner = s.__name__ if hasattr(s, '__name__') else type(s).__name__
            return f'{owner}.{cb.__func__.__name__}'
        # regular function: use qualname unless it's a lambda
        try:
            qn = cb.__qualname__
            if qn == '<lambda>':
                pass  # bare lambda, fall through to repr
            elif '<lambda>' in qn:
                return qn.replace('.<locals>.<lambda>', '.<lambda>')
            else:
                return qn
        except AttributeError:
            pass
        # fallback: repr (shows address, useful for bare lambdas)
        return repr(cb)

    # ---- public API ----

    def on(self, event, callback, ns=None):
        """Register *callback* for *event*."""
        self._listeners.setdefault(event, []).append(callback)
        if self._perf and ns:
            self._perf.register_cb(ns, callback)
        self._cb_since[id(callback)] = time.time()
        self._logger.info('[eventbus] on %s => <%s>', event, self._name(callback))

    def off(self, event, callback):
        """Remove a previously registered *callback* for *event*."""
        listeners = self._listeners.get(event, [])
        if not listeners or callback not in listeners:
            return
        try:
            listeners.remove(callback)
        except ValueError:
            pass
        if self._perf:
            self._perf.unregister_cb(callback)
        self._cb_since.pop(id(callback), None)
        self._logger.info('[eventbus] off %s => <%s>', event, self._name(callback))

    def clear(self, event):
        """Remove all listeners for *event*."""
        listeners = self._listeners.pop(event, None)
        if listeners:
            self._logger.info('[eventbus] clear %s', event)
            self._meta.pop(event, None)
            for pairs in self._namespaced.values():
                pairs[:] = [(ev, cb) for ev, cb in pairs if ev != event]
            for cb in listeners:
                self._cb_since.pop(id(cb), None)

    def emit(self, event, *args, **kwargs):
        """Publish *event* to all registered callbacks."""
        origin = kwargs.pop('_origin', None)
        tags = [event]
        if origin:
            tags.append(f'(from {origin})')
        tag = ' '.join(tags)
        if event.startswith('store:changed:') or event in ('service:registered', 'service:unregistered'):
            pass
        else:
            self._logger.info('[eventbus] emit %s', tag)
        meta = self._meta.get(event)
        if meta is None:
            self._meta[event] = {'count': 1, 'last_emit': time.time()}
        else:
            meta['count'] += 1
            meta['last_emit'] = time.time()
        listeners = self._listeners.get(event, [])
        if listeners:
            perf = self._perf
            for cb in listeners:
                ns = perf.lookup_ns(cb) if perf else ''
                try:
                    if perf and perf.enabled:
                        t0 = time.perf_counter()
                        if ns == 'app' and origin is not None and origin == 'plugin_manager':
                            cb(*args, _origin=origin, **kwargs)
                        else:
                            cb(*args, **kwargs)
                        elapsed = time.perf_counter() - t0
                        ns = perf.lookup_ns(cb)
                        perf.record_event(ns, event, elapsed)
                    else:
                        if ns == 'app' and origin is not None and origin == 'plugin_manager':
                            cb(*args, _origin=origin, **kwargs)
                        else:
                            cb(*args, **kwargs)
                except Exception:
                    self._logger.exception('[eventbus] error in callback <%s> for %s', self._name(cb), tag)

    # ---- namespaced access ----

    def module(self, ns):
        """Return a namespace-scoped handle — on/off tracked for cleanup(ns)."""
        return _EventBusModule(self, ns)

    def cleanup(self, ns):
        """Remove all listeners registered under namespace *ns*."""
        for event, callback in self._namespaced.pop(ns, []):
            self.off(event, callback)

    # ---- snapshot ----

    def snapshot(self):
        """Return a point-in-time snapshot of all active listeners.

        Returns a dict::

            {'events': {event_name: {
                'count': int, 'last_emit': float|None,
                'callbacks': [{'name': str, 'namespace': str}, ...]
            }, ...}}
        """
        cb_ns = {}
        for ns, pairs in self._namespaced.items():
            for _ev, cb in pairs:
                cb_ns[id(cb)] = ns

        events = {}
        seen = set()
        for event, cbs in self._listeners.items():
            seen.add(event)
            meta = self._meta.get(event, {})
            callbacks = []
            for cb in cbs:
                callbacks.append({
                    'name': self._name(cb),
                    'namespace': cb_ns.get(id(cb), 'app'),
                    'since': self._cb_since.get(id(cb)),
                })
            if callbacks:
                events[event] = {
                    'count': meta.get('count', 0),
                    'last_emit': meta.get('last_emit'),
                    'callbacks': callbacks,
                }
        # Include events with meta but no listeners
        for event, meta in self._meta.items():
            if event not in seen:
                events[event] = {
                    'count': meta.get('count', 0),
                    'last_emit': meta.get('last_emit'),
                    'callbacks': [],
                }
        return {'events': events}


class _EventBusModule:
    """Namespaced eventbus handle — on/off calls are tracked in the parent.
    emit / clear / cleanup pass through to the real eventbus.
    """

    __slots__ = ('_bus', '_ns')

    def __init__(self, bus, ns):
        self._bus = bus
        self._ns = ns

    def on(self, event, callback):
        self._bus.on(event, callback, ns=self._ns)
        self._bus._namespaced.setdefault(self._ns, []).append((event, callback))

    def off(self, event, callback):
        self._bus.off(event, callback)
        items = self._bus._namespaced.get(self._ns, [])
        try:
            items.remove((event, callback))
        except ValueError:
            pass

    def emit(self, event, *args, **kwargs):
        kwargs.pop('_origin', None)
        self._bus.emit(event, *args, _origin=self._ns, **kwargs)

    def __getattr__(self, name):
        return getattr(self._bus, name)
