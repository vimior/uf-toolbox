# -*- coding: utf-8 -*-
"""Lightweight pub-sub event bus."""
import time
import logging
import asyncio
import inspect
import threading
import functools
from .utils import _callback_name, _resolve_name


class EventBus:
    """Publish-subscribe event system — on / off / emit / clear.

    Used by ``AppState`` as ``app.eventbus``; ``app.on()`` / ``app.emit()``
    delegate here for convenience.
    """

    def __init__(self, perf=None, logger=None):
        self._listeners = {}
        self._namespaced = {}  # ns → [(event, callback), ...]
        self._meta = {}  # event → {count, last_emit}
        self._emit_ns = {}  # event → {ns → {count, last_emit}}
        self._cb_since = {}  # id(callback) → timestamp
        self._cb_count = {}  # id(callback) → invocation count
        self._perf = perf  # PerfMonitor instance (optional)
        self._logger = logger or logging.getLogger(__name__)
        self._is_shutting_down = False
        self._asyncio_loop = None
        self._asyncio_thread = None
        threading.Thread(target=self._asyncio_watchdog, daemon=True).start()
        time.sleep(0.1)  # Give the watchdog a moment to start the event loop thread

    def _asyncio_watchdog(self):
        """Watchdog thread to monitor the asyncio event loop."""
        while not self._is_shutting_down:
            if self._asyncio_thread is None:
                self._spawn_asyncio_thread()
            else:
                self._asyncio_thread.join(timeout=1.0)
                if not self._asyncio_thread.is_alive() and not self._is_shutting_down:
                    self._spawn_asyncio_thread()  # Restart the event loop thread
            time.sleep(1)

    def _spawn_asyncio_thread(self):
        """Spawn a watchdog thread to monitor the asyncio event loop."""
        self._asyncio_thread = threading.Thread(target=self._run_asyncio_loop, daemon=True)
        self._asyncio_thread.start()

    def _run_asyncio_loop(self):
        """Run asyncio event loop in a separate thread."""
        self._asyncio_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._asyncio_loop)
        self._logger.info('[EventLoop] asyncio event loop thread started')

        def global_exception_handler(loop, context):
            msg = context.get("exception", context["message"])
            self._logger.error('[EventLoop] Caught unhandled exception: %s', msg, exc_info=True)
        self._asyncio_loop.set_exception_handler(global_exception_handler)

        try:
            self._asyncio_loop.run_forever()
        except Exception as e:
            self._logger.error(f'[EventLoop] asyncio event loop has stopped unexpectedly: {e}', exc_info=True)
        finally:
            try:
                pending = asyncio.all_tasks(loop=self._asyncio_loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._asyncio_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                self._asyncio_loop.close()

    # ---- public API ----

    def on(self, event, callback, ns):
        """Register *callback* for *event* (no-op if already registered)."""
        event = _resolve_name(event, ns)
        final_callback = callback

        # Identify and wrap asynchronous callbacks
        if inspect.iscoroutinefunction(callback):
            @functools.wraps(callback)
            def async_wrapper(*args, **kwargs):
                if self._asyncio_loop and self._asyncio_loop.is_running():
                    asyncio.run_coroutine_threadsafe(callback(*args, **kwargs), self._asyncio_loop)
            async_wrapper.__wrapped__ = callback  # Preserve original function references
            final_callback = async_wrapper

        listeners = self._listeners.setdefault(event, [])
        # Obtain the "__qualname__" of the original callback as a unique identifier.
        # Solving the problem of the id changing every time in Bound Method
        current_qualname = getattr(callback, '__qualname__', id(callback))
        for existing_cb in listeners:
            existing_identity = getattr(existing_cb, '__wrapped__', existing_cb)
            existing_qualname = getattr(existing_identity, '__qualname__', id(existing_identity))
            if existing_qualname == current_qualname:
                return

        listeners.append(final_callback)
        if ns:
            self._namespaced.setdefault(ns, []).append((event, final_callback))
            if self._perf:
                self._perf.register_cb(ns, final_callback)
        self._cb_since[id(final_callback)] = time.time()
        self._logger.info('[eventbus] on %s → %s', event, _callback_name(final_callback))

    def off(self, event, callback, ns=None):
        """Remove a previously registered *callback* for *event*.

        If *ns* is given, also clears the namespace tracking entry
        (same bookkeeping as :meth:`on`).
        """
        if ns:
            event = _resolve_name(event, ns)
        # Obtain the "__qualname__" of the original callback as a unique identifier.
        current_qualname = getattr(callback, '__qualname__', id(callback))
        listeners = self._listeners.get(event, [])
        index = -1
        # Iterate through the list and use `__qualname__` to pinpoint the exact location (never use `list.remove`).
        for i, existing_cb in enumerate(listeners):
            existing_identity = getattr(existing_cb, '__wrapped__', existing_cb)
            existing_qualname = getattr(existing_identity, '__qualname__', id(existing_identity))
            if existing_qualname == current_qualname:
                index = i
                break
        if index < 0:
            return
        # Obtain the final callback
        callback = listeners.pop(index)
        if self._perf:
            self._perf.unregister_cb(callback)
        self._cb_since.pop(id(callback), None)
        self._cb_count.pop(id(callback), None)
        if ns:
            items = self._namespaced.get(ns, [])
            try:
                items.remove((event, callback))
            except ValueError:
                pass
        self._logger.info('[eventbus] off %s → %s', event, _callback_name(callback))

    def clear(self, event, ns=None):
        """Remove all listeners for *event*.

        If *ns* is given, the event is qualified and only that namespace's
        tracking entry is cleaned.  Otherwise all namespaces are scanned.
        """
        if ns:
            event = _resolve_name(event, ns)
        listeners = self._listeners.pop(event, None)
        if listeners:
            self._logger.info('[eventbus] clear %s', event)
            self._meta.pop(event, None)
            self._emit_ns.pop(event, None)
            if ns:
                items = self._namespaced.get(ns, [])
                items[:] = [(ev, cb) for ev, cb in items if ev != event]
            else:
                for pairs in self._namespaced.values():
                    pairs[:] = [(ev, cb) for ev, cb in pairs if ev != event]
            for cb in listeners:
                self._cb_since.pop(id(cb), None)
                self._cb_count.pop(id(cb), None)

    def emit(self, event, *args, ns, **kwargs):
        """Publish *event* to all registered callbacks.

        *kwargs* are forwarded to listeners (except *ns*, which is reserved).
        """
        event = _resolve_name(event, ns)
        tags = [event]
        if ns:
            tags.append(f'(from {ns})')
        tag = ' '.join(tags)
        # per-event stats
        meta = self._meta.get(event)
        if meta is None:
            self._meta[event] = {'count': 1, 'last_emit': time.time()}
        else:
            meta['count'] += 1
            meta['last_emit'] = time.time()
        # per-emitter stats
        if ns:
            self._emit_ns.setdefault(event, {}).setdefault(ns, {'count': 0, 'last_emit': 0})
            self._emit_ns[event][ns]['count'] += 1
            self._emit_ns[event][ns]['last_emit'] = time.time()

        listeners = self._listeners.get(event, [])
        is_noisy = event.startswith('store:changed:') or event in ('services@registered', 'services@unregistered')
        if not is_noisy:
            level = logging.DEBUG if not listeners else logging.INFO
            self._logger.log(level, '[eventbus] emit %s → %d listener(s)', tag, len(listeners))
        t_emit = time.perf_counter() if (self._perf and ns) else 0
        if listeners:
            perf = self._perf
            for cb in listeners:
                cid = id(cb)
                self._cb_count[cid] = self._cb_count.get(cid, 0) + 1
                cb_ns = perf.lookup_ns(cb) if perf else ''
                try:
                    if perf and perf.enabled:
                        t0 = time.perf_counter()
                        if event.startswith('plugins@hook:') and cb_ns in ('app', 'plugins'):
                            cb(*args, ns=ns, **kwargs)
                        else:
                            cb(*args, **kwargs)
                        elapsed = time.perf_counter() - t0
                        cb_ns = perf.lookup_ns(cb)
                        perf.record_event(cb_ns, event, elapsed)
                    else:
                        if event.startswith('plugins@hook:') and cb_ns in ('app', 'plugins'):
                            cb(*args, ns=ns, **kwargs)
                        else:
                            cb(*args, **kwargs)
                except Exception:
                    self._logger.exception('[eventbus] error in callback %s for %s', _callback_name(cb), tag)
        if t_emit:
            self._perf.record_emit(ns, event, time.perf_counter() - t_emit)

    # ---- namespaced access ----

    def module(self, ns):
        """Return a namespace-scoped handle — on/off tracked for cleanup(ns)."""
        return _EventBusModule(self, ns)

    def cleanup(self, ns):
        """Remove all listeners registered under namespace *ns*."""
        for event, callback in self._namespaced.pop(ns, []):
            self.off(event, callback)

    # ---- snapshot ----

    def snapshot(self, ns=None):
        """Return a point-in-time snapshot of all active listeners.

        If *ns* is given, only events qualified under that namespace
        are returned (callbacks are still shown regardless of their
        own namespace, so cross-ns subscribers are visible).

        Returns::

            {
                'events': {
                    'ns@event': {
                        'count':      int,
                        'last_emit':  float | None,
                        'callbacks': [
                            {
                                'name':      str,
                                'namespace': str,
                                'since':     float,
                                'count':     int,
                            },
                        ],
                        'emit_ns': [
                            {
                                'namespace':  str,
                                'count':      int,
                                'last_emit':  float,
                            },
                        ],
                    },
                },
            }
        """
        cb_ns = {}
        for owner, pairs in self._namespaced.items():
            for _ev, cb in pairs:
                cb_ns[id(cb)] = owner

        events = {}
        seen = set()
        for event, cbs in self._listeners.items():
            seen.add(event)
            meta = self._meta.get(event, {})
            callbacks = []
            for cb in cbs:
                callbacks.append({
                    'name': _callback_name(cb),
                    'namespace': cb_ns.get(id(cb), 'app'),
                    'since': self._cb_since.get(id(cb)),
                    'count': self._cb_count.get(id(cb), 0),
                })
            emit_ns = []
            for emit_ns_name, od in self._emit_ns.get(event, {}).items():
                emit_ns.append({
                    'namespace': emit_ns_name,
                    'count': od['count'],
                    'last_emit': od.get('last_emit'),
                })
            emit_ns.sort(key=lambda o: o['count'], reverse=True)
            if callbacks:
                events[event] = {
                    'count': meta.get('count', 0),
                    'last_emit': meta.get('last_emit'),
                    'callbacks': callbacks,
                    'emit_ns': emit_ns,
                }
        # Include events with meta but no listeners
        for event, meta in self._meta.items():
            if event not in seen:
                emit_ns = []
                for emit_ns_name, od in self._emit_ns.get(event, {}).items():
                    emit_ns.append({
                        'namespace': emit_ns_name,
                        'count': od['count'],
                        'last_emit': od.get('last_emit'),
                    })
                emit_ns.sort(key=lambda o: o['count'], reverse=True)
                events[event] = {
                    'count': meta.get('count', 0),
                    'last_emit': meta.get('last_emit'),
                    'callbacks': [],
                    'emit_ns': emit_ns,
                }
        if ns:
            prefix = ns + '@'
            events = {e: v for e, v in events.items() if e.startswith(prefix)}
        return {'events': events}


class _EventBusModule:
    """Namespaced eventbus handle — ns is auto-injected, event prefixing
    is handled by :class:`EventBus` via :func:`_resolve_name`.
    """

    __slots__ = ('_bus', '_ns')

    def __init__(self, bus, ns):
        self._bus = bus
        self._ns = ns

    def on(self, event, callback):
        if event.startswith('store:changed:'):
            self._bus._logger.warning(
                '[eventbus] direct store:changed: listener — prefer store.subscribe()')
        elif event == 'services@registered':
            self._bus._logger.warning(
                '[eventbus] direct services@registered listener — prefer services.on_registered()')
        elif event == 'services@unregistered':
            self._bus._logger.warning(
                '[eventbus] direct services@unregistered listener — prefer services.on_unregistered()')
        self._bus.on(event, callback, ns=self._ns)

    def off(self, event, callback):
        self._bus.off(event, callback, ns=self._ns)

    def emit(self, event, *args, **kwargs):
        kwargs.pop('ns', None)  # prevent caller from spoofing namespace
        self._bus.emit(event, *args, ns=self._ns, **kwargs)

    def clear(self, event):
        self._bus.clear(event, ns=self._ns)

    def cleanup(self):
        self._bus.cleanup(self._ns)

    def snapshot(self):
        return self._bus.snapshot(ns=self._ns)

    def __getattr__(self, name):
        return getattr(self._bus, name)
