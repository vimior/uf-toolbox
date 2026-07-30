# -*- coding: utf-8 -*-
"""Unit tests for Store — namespace-scoped keys, write protection, ownership."""

import unittest

from common.infra.eventbus import EventBus
from common.infra.utils import _resolve_name, _namespace_of
from common.infra.store import Store


class TestResolveName(unittest.TestCase):
    """_resolve_name / _namespace_of for store keys."""

    def test_bare_name_scoped(self):
        self.assertEqual(_resolve_name('my_key', 'plugin_a'), 'plugin_a@my_key')
        self.assertEqual(_resolve_name('x', 'plugin_b'), 'plugin_b@x')

    def test_at_present_passthrough(self):
        self.assertEqual(_resolve_name('other@data', 'plugin_a'), 'other@data')

    def test_namespace_of(self):
        self.assertEqual(_namespace_of('plugin_a@k1'), 'plugin_a')
        self.assertEqual(_namespace_of('bare_key'), '')


class TestWriteProtection(unittest.TestCase):
    """Store.commit — rejects cross-namespace writes."""

    def setUp(self):
        self.store = Store(EventBus())

    def test_own_namespace_allowed(self):
        self.store.commit('plugin_a@k1', 1, ns='plugin_a')
        self.assertEqual(self.store.get('plugin_a@k1'), 1)

    def test_cross_namespace_rejected(self):
        self.store.commit('plugin_a@k1', 1, ns='plugin_a')
        self.store.commit('plugin_a@k1', 999, ns='plugin_b')
        self.assertEqual(self.store.get('plugin_a@k1'), 1)

    def test_cross_namespace_rejected_different_keys(self):
        self.store.commit('ns_a@data', 'original', ns='ns_a')
        self.store.commit('ns_a@data', 'hijacked', ns='ns_b')
        self.assertEqual(self.store.get('ns_a@data'), 'original')


class TestOwnership(unittest.TestCase):
    """Store ownership is determined by key's @ prefix."""

    def setUp(self):
        self.store = Store(EventBus())

    def test_ownership_set_from_key_prefix(self):
        self.store.commit('plugin_a@data', 42, ns='plugin_a')
        self.assertEqual(self.store._owners.get('plugin_a@data'), 'plugin_a')

    def test_ownership_from_short_name_auto_qualified(self):
        self.store.commit('data', 42, ns='plugin_a')
        self.assertEqual(self.store._owners.get('plugin_a@data'), 'plugin_a')


class TestModuleAPI(unittest.TestCase):
    """_StoreModule commit/get/subscribe with auto-prefixing."""

    def setUp(self):
        self.store = Store(EventBus())

    def test_commit_get(self):
        mod = self.store.module('plugin_a')
        mod.commit('count', 10)
        self.assertEqual(mod.get('count'), 10)

    def test_get_cross_ns(self):
        mod_a = self.store.module('plugin_a')
        mod_b = self.store.module('plugin_b')
        mod_a.commit('status', 'ready')
        self.assertEqual(mod_b.get('plugin_a@status'), 'ready')

    def test_subscribe(self):
        mod = self.store.module('plugin_a')
        calls = []

        def on_change(value, old):
            calls.append((value, old))
        mod.subscribe('counter', on_change)
        mod.commit('counter', 5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 5)

    def test_subscribe_cross_ns(self):
        mod_a = self.store.module('plugin_a')
        mod_b = self.store.module('plugin_b')
        calls = []
        mod_b.subscribe('plugin_a@status', lambda v, o: calls.append(v))
        mod_a.commit('status', 'online')
        self.assertEqual(calls, ['online'])

    def test_dump(self):
        mod = self.store.module('plugin_a')
        mod.commit('a', 1)
        mod.commit('b', 2)
        dumped = mod.dump()
        self.assertEqual(len(dumped), 2)
        self.assertIn(1, dumped.values())
        self.assertIn(2, dumped.values())

    def test_keys(self):
        mod = self.store.module('plugin_a')
        mod.commit('k1', 1)
        mod.commit('k2', 2)
        keys = mod.keys()
        self.assertEqual(len(keys), 2)
        self.assertIn('plugin_a@k1', keys)
        self.assertIn('plugin_a@k2', keys)

    def test_keys_filter_by_owner(self):
        mod_a = self.store.module('plugin_a')
        mod_b = self.store.module('plugin_b')
        mod_a.commit('only_a', 1)
        mod_b.commit('only_b', 2)
        self.assertIn('plugin_b@only_b', mod_b.keys())
        self.assertNotIn('plugin_a@only_a', mod_b.keys())


class TestCleanup(unittest.TestCase):
    """Store.cleanup — only removes own namespaced keys."""

    def setUp(self):
        self.store = Store(EventBus())

    def test_cleanup_removes_own_keys(self):
        mod_a = self.store.module('plugin_a')
        mod_b = self.store.module('plugin_b')
        mod_a.commit('data', 1)
        mod_b.commit('data', 2)
        self.store.cleanup('plugin_a')
        self.assertIsNone(self.store.get('plugin_a@data'))
        self.assertEqual(self.store.get('plugin_b@data'), 2)

    def test_cleanup_not_affected_by_cross_write_attempt(self):
        self.store.commit('plugin_a@data', 1, ns='plugin_a')
        self.store.commit('plugin_a@data', 999, ns='plugin_b')  # rejected
        self.store.cleanup('plugin_a')
        self.assertIsNone(self.store.get('plugin_a@data'))


if __name__ == '__main__':
    unittest.main()
