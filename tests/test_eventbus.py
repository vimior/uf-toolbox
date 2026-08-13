# -*- coding: utf-8 -*-
"""Unit tests for EventBus — module layer delegates, core resolves names."""

import unittest

from common.infra.utils import _resolve_name
from common.infra.eventbus import EventBus


class TestResolveName(unittest.TestCase):
    """_resolve_name — @ present → qualified, else ns@name."""

    def test_bare_name_scoped(self):
        self.assertEqual(_resolve_name('timer', 'plugin_a'), 'plugin_a@timer')
        self.assertEqual(_resolve_name('ready', 'plugin_b'), 'plugin_b@ready')

    def test_at_present_fully_qualified(self):
        self.assertEqual(_resolve_name('other@data', 'plugin_a'), 'other@data')
        self.assertEqual(_resolve_name('services@registered', 'plugin_a'), 'services@registered')

    def test_different_ns(self):
        self.assertEqual(_resolve_name('x', 'plugin_a'), 'plugin_a@x')
        self.assertEqual(_resolve_name('x', 'plugin_b'), 'plugin_b@x')


class TestOn(unittest.TestCase):
    """Module.on — delegates to core which resolves + tracks for cleanup."""

    def setUp(self):
        self.bus = EventBus()

    def test_on_registers_resolved_name(self):
        mod = self.bus.module('plugin_a')
        cb = lambda *_a, **_kw: None
        mod.on('timer', cb)
        self.assertIn(cb, self.bus._listeners.get('plugin_a@timer', []))

    def test_on_tracks_in_namespaced(self):
        mod = self.bus.module('plugin_a')
        cb = lambda *_a, **_kw: None
        mod.on('timer', cb)
        entries = self.bus._namespaced.get('plugin_a', [])
        self.assertTrue(any(e[0] == 'plugin_a@timer' and e[1] is cb for e in entries))

    def test_on_cross_ns_at_present(self):
        mod = self.bus.module('plugin_b')
        cb = lambda *_a, **_kw: None
        mod.on('plugin_a@data_ready', cb)
        self.assertIn(cb, self.bus._listeners.get('plugin_a@data_ready', []))


class TestEmit(unittest.TestCase):
    """Module.emit — delegates to core which resolves event name."""

    def setUp(self):
        self.bus = EventBus()

    def test_emit_resolves_bare_name(self):
        mod = self.bus.module('plugin_a')
        called = []
        mod.on('timer', lambda *a: called.append(a))
        mod.emit('timer', 42)
        self.assertEqual(called, [(42,)])

    def test_emit_at_present_passthrough(self):
        mod = self.bus.module('plugin_a')
        called = []
        mod.on('plugins@stop', lambda *a: called.append(a))
        mod.emit('plugins@stop', 'target')
        self.assertEqual(called, [('target',)])

    def test_emit_delivers_to_all_listeners(self):
        mod_a = self.bus.module('plugin_a')
        mod_b = self.bus.module('plugin_b')
        r_a, r_b = [], []

        def on_a(*a):
            r_a.append(a)

        def on_b(*a):
            r_b.append(a)

        mod_a.on('timer', on_a)
        mod_b.on('plugin_a@timer', on_b)  # 跨 ns 监听
        mod_a.emit('timer', 42)
        self.assertEqual(r_a, [(42,)])
        self.assertEqual(r_b, [(42,)])


class TestOff(unittest.TestCase):
    """Module.off — resolves and removes correctly."""

    def setUp(self):
        self.bus = EventBus()

    def test_off_removes_from_listeners_and_namespaced(self):
        mod = self.bus.module('plugin_a')
        cb = lambda *_a, **_kw: None
        mod.on('timer', cb)
        self.assertIn(cb, self.bus._listeners.get('plugin_a@timer', []))
        mod.off('timer', cb)
        self.assertNotIn(cb, self.bus._listeners.get('plugin_a@timer', []))
        entries = self.bus._namespaced.get('plugin_a', [])
        self.assertFalse(any(e[1] is cb for e in entries))

    def test_off_cross_ns(self):
        mod = self.bus.module('plugin_b')
        cb = lambda *_a, **_kw: None
        mod.on('plugin_a@data_ready', cb)
        mod.off('plugin_a@data_ready', cb)
        self.assertNotIn(cb, self.bus._listeners.get('plugin_a@data_ready', []))


class TestCleanup(unittest.TestCase):
    """EventBus.cleanup — only removes own namespace entries."""

    def setUp(self):
        self.bus = EventBus()

    def test_cleanup_removes_only_own_scope(self):
        mod_a = self.bus.module('plugin_a')
        mod_b = self.bus.module('plugin_b')

        def cb_a(*_a, **_kw):
            pass

        def cb_b(*_a, **_kw):
            pass

        mod_a.on('timer', cb_a)
        mod_b.on('plugin_a@timer', cb_b)  # 跨 ns 监听, cleanup('plugin_a') 不应删除
        self.bus.cleanup('plugin_a')
        self.assertNotIn(cb_a, self.bus._listeners.get('plugin_a@timer', []))
        self.assertIn(cb_b, self.bus._listeners.get('plugin_a@timer', []))
        self.assertNotIn('plugin_a', self.bus._namespaced)
        self.assertEqual(len(self.bus._namespaced.get('plugin_b', [])), 1)

    def test_cleanup_all_own_entries(self):
        mod = self.bus.module('plugin_a')
        cb1 = lambda *_a, **_kw: None
        cb2 = lambda *_a, **_kw: None
        mod.on('timer', cb1)
        mod.on('ready', cb2)
        self.bus.cleanup('plugin_a')
        self.assertNotIn('plugin_a', self.bus._namespaced)
        self.assertNotIn(cb1, self.bus._listeners.get('plugin_a@timer', []))
        self.assertNotIn(cb2, self.bus._listeners.get('plugin_a@ready', []))


if __name__ == '__main__':
    unittest.main()
