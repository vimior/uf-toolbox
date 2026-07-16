# -*- coding: utf-8 -*-
"""Lightweight pub-sub event bus."""


class EventBus:
    """Publish-subscribe event system — on / off / emit / clear.

    Used by ``AppState`` as ``app.eventbus``; ``app.on()`` / ``app.emit()``
    delegate here for convenience.
    """

    def __init__(self):
        self._listeners = {}

    # ---- helpers ----

    @staticmethod
    def _name(cb):
        """Human-readable name for *cb*."""
        # bound method: ClassName.method
        if hasattr(cb, '__self__') and hasattr(cb, '__func__'):
            return f'{type(cb.__self__).__name__}.{cb.__func__.__name__}'
        # regular function: use qualname unless it's a lambda
        try:
            qn = cb.__qualname__
            if qn != '<lambda>':
                return qn
        except AttributeError:
            pass
        # fallback: repr (shows address, useful for lambdas)
        return repr(cb)

    # ---- public API ----

    def on(self, event, callback):
        """Register *callback* for *event*."""
        self._listeners.setdefault(event, []).append(callback)
        print(f'[eventbus] on {event} => <{self._name(callback)}>')

    def off(self, event, callback):
        """Remove a previously registered *callback* for *event*."""
        listeners = self._listeners.get(event, [])
        if not listeners or callback not in listeners:
            return
        try:
            listeners.remove(callback)
        except ValueError:
            pass
        print(f'[eventbus] off {event} => <{self._name(callback)}>')

    def clear(self, event):
        """Remove all listeners for *event*."""
        listeners = self._listeners.pop(event, None)
        if listeners:
            print(f'[eventbus] clear {event}')

    def emit(self, event, *args, **kwargs):
        """Publish *event* to all registered callbacks."""
        listeners = self._listeners.get(event, [])
        if listeners:
            print(f'[eventbus] emit {event}')
            for cb in listeners:
                cb(*args, **kwargs)
