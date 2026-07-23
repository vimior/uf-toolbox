# -*- coding: utf-8 -*-
"""Lightweight performance monitor for per-plugin and total overhead tracking."""
import os
import time
import logging


class PerfMonitor:
    """Tracks per-namespace (plugin) event/service/store overhead.

    Integrates with EventBus, Services, and Store via lightweight hooks.
    Accessible via ``app._infra.perf`` for inspection plugins.
    """

    def __init__(self, logger=None):
        self._logger = logger or logging.getLogger(__name__)
        self.enabled = True
        self._start_time = time.perf_counter()
        # ns -> {event_name -> {'count': N, 'total_s': T, 'max_s': M}}
        self._event_stats = {}
        # ns -> {service_name -> {'count': N, 'total_s': T, 'max_s': M}}
        self._service_stats = {}
        # ns -> {'commits': N, 'subscribes': N}
        self._store_stats = {}
        # Reverse map: id(callback) -> ns (for event attribution)
        self._cb_ns = {}

    # ---- helpers ----

    @staticmethod
    def _now():
        return time.perf_counter()

    def uptime(self):
        """Seconds since PerfMonitor was created (≈ app uptime)."""
        return self._now() - self._start_time

    def _ensure_ns(self, stats_dict, ns):
        if ns not in stats_dict:
            stats_dict[ns] = {}

    # ---- callback-to-namespace registry (called by EventBus) ----

    def register_cb(self, ns, callback):
        """Associate a callback with a namespace for later attribution."""
        self._cb_ns[id(callback)] = ns

    def unregister_cb(self, callback):
        """Remove callback-to-namespace mapping."""
        self._cb_ns.pop(id(callback), None)

    def lookup_ns(self, callback):
        """Return the namespace for *callback*, or 'app' if unknown."""
        return self._cb_ns.get(id(callback), 'app')

    # ---- event timing ----

    def record_event(self, ns, event_name, elapsed_s):
        """Record an event callback execution."""
        if not self.enabled:
            return
        self._ensure_ns(self._event_stats, ns)
        entry = self._event_stats[ns].get(event_name)
        if entry is None:
            entry = {'count': 0, 'total_s': 0.0, 'max_s': 0.0}
            self._event_stats[ns][event_name] = entry
        entry['count'] += 1
        entry['total_s'] += elapsed_s
        if elapsed_s > entry['max_s']:
            entry['max_s'] = elapsed_s

    # ---- service timing ----

    def record_service(self, ns, service_name, elapsed_s):
        """Record a service call."""
        if not self.enabled:
            return
        self._ensure_ns(self._service_stats, ns)
        entry = self._service_stats[ns].get(service_name)
        if entry is None:
            entry = {'count': 0, 'total_s': 0.0, 'max_s': 0.0}
            self._service_stats[ns][service_name] = entry
        entry['count'] += 1
        entry['total_s'] += elapsed_s
        if elapsed_s > entry['max_s']:
            entry['max_s'] = elapsed_s

    # ---- store counters ----

    def record_store_commit(self, ns):
        """Record a store write."""
        if not self.enabled:
            return
        self._ensure_ns(self._store_stats, ns)
        entry = self._store_stats[ns]
        entry['commits'] = entry.get('commits', 0) + 1

    def record_store_subscribe(self, ns):
        """Record a store subscription."""
        if not self.enabled:
            return
        self._ensure_ns(self._store_stats, ns)
        entry = self._store_stats[ns]
        entry['subscribes'] = entry.get('subscribes', 0) + 1

    # ---- summary ----

    def snapshot(self):
        """Return a point-in-time snapshot of all collected stats.

        Returns a dict:
            {
                'uptime_s': float,
                'process': {'cpu_time_s': float, 'memory_mb': float | None},
                'namespaces': {
                    ns: {
                        'events': {name: {count, total_s, max_s}, ...},
                        'services': {name: {count, total_s, max_s}, ...},
                        'store': {commits: N, subscribes: N},
                    }, ...
                },
                'totals': {
                    'event_calls': N, 'event_total_s': T,
                    'service_calls': N, 'service_total_s': T,
                    'store_commits': N, 'store_subscribes': N,
                },
            }
        """
        result = {
            'uptime_s': self.uptime(),
            'process': self._process_info(),
            'namespaces': {},
            'totals': {
                'event_calls': 0, 'event_total_s': 0.0,
                'service_calls': 0, 'service_total_s': 0.0,
                'store_commits': 0, 'store_subscribes': 0,
            },
        }

        # Collect all namespaces
        all_ns = set(self._event_stats.keys()) | set(self._service_stats.keys()) | set(self._store_stats.keys())

        for ns in sorted(all_ns):
            ns_data = {
                'events': dict(self._event_stats.get(ns, {})),
                'services': dict(self._service_stats.get(ns, {})),
                'store': dict(self._store_stats.get(ns, {})),
            }
            result['namespaces'][ns] = ns_data

            for evt in ns_data['events'].values():
                result['totals']['event_calls'] += evt['count']
                result['totals']['event_total_s'] += evt['total_s']
            for svc in ns_data['services'].values():
                result['totals']['service_calls'] += svc['count']
                result['totals']['service_total_s'] += svc['total_s']
            result['totals']['store_commits'] += ns_data['store'].get('commits', 0)
            result['totals']['store_subscribes'] += ns_data['store'].get('subscribes', 0)

        return result

    def reset(self):
        """Clear all collected stats (but keep callback-to-ns mappings and uptime clock)."""
        self._event_stats.clear()
        self._service_stats.clear()
        self._store_stats.clear()

    # ---- process info ----

    def _process_info(self):
        """Return {cpu_time_s, memory_mb} for the current process."""
        info = {'cpu_time_s': time.process_time(), 'memory_mb': None}
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            mem = proc.memory_full_info()
            info['memory_mb'] = round(mem.uss / (1024 * 1024), 2)
        except Exception:
            self._logger.debug('psutil not available, memory info skipped')
        return info
