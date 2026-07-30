# -*- coding: utf-8 -*-
"""Unit tests for Services — registration, call, event names, cleanup."""

import unittest

from common.infra.eventbus import EventBus
from common.infra.services import Services


class TestEventNames(unittest.TestCase):
    """Services uses services@registered / services@unregistered events."""

    def setUp(self):
        self.bus = EventBus()
        self.services = Services(self.bus)

    def test_register_emits_services_at_registered(self):
        called = []
        self.bus.on('services@registered', lambda name: called.append(name), ns='test')
        self.services.register('func', lambda: 42, ns='test')
        self.assertEqual(called, ['test@func'])

    def test_unregister_emits_services_at_unregistered(self):
        called = []
        self.bus.on('services@unregistered', lambda name: called.append(name), ns='test')
        self.services.register('func', lambda: 42, ns='test')
        self.services.unregister('test@func', ns='test')
        self.assertEqual(called, ['test@func'])

    def test_on_registered_uses_correct_event(self):
        called = []
        self.services.on_registered(lambda name: called.append(name), ns='test')
        self.services.register('svc', lambda: None, ns='other')
        self.assertEqual(called, ['other@svc'])

    def test_on_unregistered_uses_correct_event(self):
        called = []
        self.services.on_unregistered(lambda name: called.append(name), ns='test')
        self.services.register('svc', lambda: None, ns='other')
        self.services.unregister('other@svc', ns='other')
        self.assertEqual(called, ['other@svc'])


class TestRegisterCall(unittest.TestCase):
    """Basic register / call / has / names."""

    def setUp(self):
        self.services = Services(EventBus())

    def test_register_and_call(self):
        self.services.register('add', lambda a, b: a + b, ns='math')
        self.assertEqual(self.services.call('math@add', 1, 2, ns='caller'), 3)

    def test_call_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.services.call('nonexistent', ns='caller')

    def test_has(self):
        self.services.register('func', lambda: None, ns='test')
        self.assertTrue(self.services.has('test@func'))
        self.assertFalse(self.services.has('missing@func'))

    def test_names(self):
        self.services.register('f1', lambda: None, ns='a')
        self.services.register('f2', lambda: None, ns='b')
        self.assertIn('a@f1', self.services.names())
        self.assertIn('b@f2', self.services.names())
        self.assertEqual(self.services.names(ns='a'), ['a@f1'])

    def test_unregister_with_cross_ns_protection(self):
        self.services.register('func', lambda: None, ns='test')
        self.services.unregister('test@func', ns='test')
        self.assertFalse(self.services.has('test@func'))


class TestModule(unittest.TestCase):
    """_ServiceModule auto-prefixes on register/call/unregister."""

    def setUp(self):
        self.services = Services(EventBus())

    def test_module_register_prefixes(self):
        mod = self.services.module('plugin_a')
        mod.register('do_sth', lambda: 42)
        self.assertTrue(self.services.has('plugin_a@do_sth'))
        self.assertEqual(self.services.call('plugin_a@do_sth', ns='caller'), 42)

    def test_module_call_short_name_auto_prefix(self):
        mod_a = self.services.module('plugin_a')
        mod_b = self.services.module('plugin_b')
        mod_a.register('get_data', lambda: 'data_from_a')
        result = mod_b.call('plugin_a@get_data')
        self.assertEqual(result, 'data_from_a')

    def test_module_unregister(self):
        mod = self.services.module('plugin_a')
        mod.register('do_sth', lambda: None)
        mod.unregister('do_sth')
        self.assertFalse(self.services.has('plugin_a@do_sth'))


class TestCleanup(unittest.TestCase):
    """Services.cleanup — removes all traces of an owner."""

    def setUp(self):
        self.services = Services(EventBus())

    def test_cleanup_removes_own_services(self):
        mod_a = self.services.module('plugin_a')
        mod_b = self.services.module('plugin_b')
        mod_a.register('func', lambda: None)
        mod_b.register('func', lambda: None)
        self.services.cleanup('plugin_a')
        self.assertFalse(self.services.has('plugin_a@func'))
        self.assertTrue(self.services.has('plugin_b@func'))

    def test_cleanup_removes_subscriptions(self):
        """Event listener cleanup is handled by EventBus.cleanup(ns),
        called by Infrastructure.cleanup.  Services.cleanup only
        removes registered services."""
        called = []
        self.services.on_registered(lambda name: called.append(name), ns='plugin_a')
        # Services cleanup does not remove event listeners —
        # that's EventBus.cleanup's job (called by Infrastructure).
        self.services.cleanup('plugin_a')
        # Callback still fires because EventBus still has it
        self.services.register('svc', lambda: None, ns='other')
        self.assertEqual(called, ['other@svc'])
        # EventBus.cleanup removes the listener
        self.services.on_registered(lambda name: called.append(name), ns='plugin_a')
        called.clear()
        self.services._eventbus.cleanup('plugin_a')
        self.services.register('svc2', lambda: None, ns='other')
        self.assertEqual(called, [])


if __name__ == '__main__':
    unittest.main()
