# -*- coding: utf-8 -*-
"""Unit tests for plugin base classes — GuiPlugin, ServicePlugin."""

import unittest
from unittest.mock import MagicMock, patch

from plugins.plugin import GuiPlugin, ServicePlugin, PluginBase


# ===========================================================================
#  ServicePlugin  (no Tk dependency — fully testable)
# ===========================================================================


class TestServicePluginDefaults(unittest.TestCase):
    """ServicePlugin class-level defaults."""

    def test_default_name(self):
        self.assertEqual(ServicePlugin.name, 'Unnamed Service')

    def test_default_namespace(self):
        self.assertIsNone(ServicePlugin.namespace)

    def test_default_priority(self):
        self.assertEqual(ServicePlugin.priority, 0)

    def test_default_auto_start(self):
        self.assertFalse(ServicePlugin.auto_start)


class TestServicePluginInit(unittest.TestCase):
    """ServicePlugin.__init__ — stores the namespaced app passed by Handle."""

    def setUp(self):
        self.mod = MagicMock()

    def test_store_set_from_module(self):
        svc = ServicePlugin(app=self.mod)
        self.assertIs(svc.store, self.mod.store)

    def test_services_set_from_module(self):
        svc = ServicePlugin(app=self.mod)
        self.assertIs(svc.services, self.mod.services)

    def test_app_set(self):
        svc = ServicePlugin(app=self.mod)
        self.assertIs(svc.app, self.mod)


class TestServicePluginLifecycle(unittest.TestCase):
    """Default on_start / on_stop are no-ops."""

    def test_on_start_noop(self):
        svc = ServicePlugin(app=MagicMock())
        self.assertIsNone(svc.on_start())

    def test_on_stop_noop(self):
        svc = ServicePlugin(app=MagicMock())
        self.assertIsNone(svc.on_stop())


# ===========================================================================
#  GuiPlugin  (tk.Toplevel — mock to avoid Tk dependency)
# ===========================================================================


class TestGuiPluginDefaults(unittest.TestCase):
    """GuiPlugin class-level defaults."""

    def test_default_name(self):
        self.assertEqual(GuiPlugin.name, 'Unnamed Plugin')

    def test_default_namespace(self):
        self.assertIsNone(GuiPlugin.namespace)

    def test_default_use_app_icon(self):
        self.assertTrue(GuiPlugin.use_app_icon)

    def test_default_fixed_position(self):
        self.assertTrue(GuiPlugin.fixed_position)

    def test_default_fixed_size(self):
        self.assertTrue(GuiPlugin.fixed_size)

    def test_default_reload(self):
        self.assertTrue(GuiPlugin.reload)

    def test_default_priority(self):
        self.assertEqual(GuiPlugin.priority, 0)

    def test_default_auto_start(self):
        self.assertFalse(GuiPlugin.auto_start)

    def test_default_start_hidden(self):
        self.assertFalse(GuiPlugin.start_hidden)


class TestGuiPluginInit(unittest.TestCase):
    """GuiPlugin.__init__ — stores the namespaced app passed by Handle."""

    def setUp(self):
        self.mock_tk_init = patch('tkinter.Toplevel.__init__').start()
        # AppToplevel.__init__ 有 withdraw/after 等真实 Tk 调用, 一并跳过
        self.mock_app_top = patch(
            'plugins.plugin.AppToplevel.__init__', return_value=None).start()
        self.addCleanup(patch.stopall)

    def test_store_set_from_module(self):
        mod = MagicMock()
        gui = GuiPlugin(parent=None, app=mod)
        self.assertIs(gui.store, mod.store)

    def test_services_set_from_module(self):
        mod = MagicMock()
        gui = GuiPlugin(parent=None, app=mod)
        self.assertIs(gui.services, mod.services)

    def test_app_set(self):
        mod = MagicMock()
        gui = GuiPlugin(parent=None, app=mod)
        self.assertIs(gui.app, mod)


class TestGuiPluginLifecycle(unittest.TestCase):
    """Default on_show / on_hide / on_destroy are no-ops."""

    def setUp(self):
        self.mock_tk_init = patch('tkinter.Toplevel.__init__').start()
        self.mock_app_top = patch(
            'plugins.plugin.AppToplevel.__init__', return_value=None).start()
        self.addCleanup(patch.stopall)

    def test_on_show_noop(self):
        gui = GuiPlugin(parent=None, app=MagicMock())
        self.assertIsNone(gui.on_show())

    def test_on_hide_noop(self):
        gui = GuiPlugin(parent=None, app=MagicMock())
        self.assertIsNone(gui.on_hide())

    def test_on_destroy_noop(self):
        gui = GuiPlugin(parent=None, app=MagicMock())
        self.assertIsNone(gui.on_destroy())


# ===========================================================================
#  PluginBase alias
# ===========================================================================


class TestPluginBaseAlias(unittest.TestCase):
    """PluginBase == GuiPlugin (backward compatibility)."""

    def test_plugin_base_is_gui_plugin(self):
        self.assertIs(PluginBase, GuiPlugin)


# ===========================================================================
#  Custom subclass pattern
# ===========================================================================


class TestCustomPlugin(unittest.TestCase):
    """Verify class attributes are inherited correctly."""

    def setUp(self):
        self.mock_tk_init = patch('tkinter.Toplevel.__init__').start()
        self.mock_app_top = patch(
            'plugins.plugin.AppToplevel.__init__', return_value=None).start()
        self.addCleanup(patch.stopall)

    def test_custom_gui_plugin_attrs(self):
        class MyPlugin(GuiPlugin):
            name = 'My Plugin'
            namespace = 'my_plugin'
            priority = 100
            reload = False
            fixed_position = False
            fixed_size = False
            use_app_icon = False
            auto_start = True
            start_hidden = True

        gui = MyPlugin(parent=None, app=MagicMock())
        self.assertEqual(gui.name, 'My Plugin')
        self.assertEqual(gui.namespace, 'my_plugin')
        self.assertEqual(gui.priority, 100)
        self.assertFalse(gui.reload)
        self.assertFalse(gui.fixed_position)
        self.assertFalse(gui.fixed_size)
        self.assertFalse(gui.use_app_icon)
        self.assertTrue(gui.auto_start)
        self.assertTrue(gui.start_hidden)

    def test_custom_service_plugin_attrs(self):
        class MyService(ServicePlugin):
            name = 'My Service'
            namespace = 'my_service'
            priority = 10
            auto_start = True

        svc = MyService(app=MagicMock())
        self.assertEqual(svc.name, 'My Service')
        self.assertEqual(svc.namespace, 'my_service')
        self.assertEqual(svc.priority, 10)
        self.assertTrue(svc.auto_start)


if __name__ == '__main__':
    unittest.main()
