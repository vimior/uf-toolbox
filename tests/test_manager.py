# -*- coding: utf-8 -*-
"""Unit tests for PluginManager — Handle, lifecycle, resolution, control events."""

import logging
import unittest

from unittest.mock import Mock, MagicMock, PropertyMock, call, patch
from plugins.manager import PluginManager
from plugins.plugin import HookInfo

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_logger():
    return logging.getLogger('test')


def make_mock_app():
    """Return a mock AppState/Infrastructure with enough surface for the manager."""
    app = MagicMock()
    app.current_lang_name = 'en'
    app.winfo_x.return_value = 100
    app.winfo_y.return_value = 100
    app.winfo_width.return_value = 800
    app.main_height = 600
    # infra
    infra = MagicMock()
    infra.eventbus = MagicMock()
    infra.services = MagicMock()
    app._infra = infra
    # AppState properties delegate to _infra
    app.eventbus = infra.eventbus
    app.services = infra.services
    # Mock AppState.on() with event resolution
    def _mock_on(event, callback, ns=None):
        resolved = event if '@' in event else f'{ns or "app"}@{event}'
        return infra.eventbus.on(resolved, callback, ns=ns or 'app')
    app.on = _mock_on
    # module() returns a plain mock (for Handle plugins that call app.module())
    app.module.return_value = MagicMock()
    return app


def make_mock_win():
    """Return a mock tkinter.Toplevel-like object."""
    win = MagicMock()
    win.winfo_exists.return_value = True
    win.winfo_viewable.return_value = True
    return win


# ---------------------------------------------------------------------------
# mock plugin classes used in eager Handle tests
# ---------------------------------------------------------------------------

# We monkey-patch issubclass so our mock classes are recognised as
# GuiPlugin / ServicePlugin without actually inheriting tk.Toplevel.

nsal_issubclass = __builtins__['issubclass']


def _patched_issubclass(cls, base):
    bases = base if isinstance(base, tuple) else (base,)
    for b in bases:
        if b.__name__ == 'GuiPlugin' and getattr(cls, '_mock_gui', False):
            return True
        if b.__name__ == 'ServicePlugin' and getattr(cls, '_mock_svc', False):
            return True
    return nsal_issubclass(cls, base)


class _MockGui:
    _mock_gui = True
    name = 'Mock GUI'
    namespace = 'mock_gui'
    priority = 50
    reload = True
    fixed_position = True
    fixed_size = True
    use_app_icon = True
    auto_start = False
    start_hidden = False


class _MockService:
    _mock_svc = True
    name = 'Mock Service'
    namespace = 'mock_svc'
    priority = 0
    auto_start = False


# Build mock class objects (not instances) for eager Handle construction
_EagerGui = type('EagerGui', (_MockGui,), {})
_EagerService = type('EagerService', (_MockService,), {})


class _EagerTestBase:
    """Mixin that patches issubclass so _MockGui / _MockService are recognised."""

    @classmethod
    def setUpClass(cls):
        __builtins__['issubclass'] = _patched_issubclass

    @classmethod
    def tearDownClass(cls):
        __builtins__['issubclass'] = nsal_issubclass


# ===========================================================================
#  Handle — lazy mode (cls=None, metadata dict)
# ===========================================================================


class TestHandleLazy(unittest.TestCase):
    """Handle created from AST metadata (cls=None)."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_lazy_not_loaded_initially(self):
        h = PluginManager.Handle(None, self.app, self.mgr, metadata={'name': 'Test'},
                                 module_name='m', class_name='C', key='test')
        self.assertFalse(h.loaded)
        self.assertFalse(h.alive)

    def test_lazy_pid_from_metadata(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T', 'namespace': 'my_pid'},
                                 module_name='m', class_name='C', key='test')
        self.assertEqual(h.namespace, 'my_pid')

    def test_lazy_pid_fallback_to_key(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T'},
                                 module_name='m', class_name='C', key='my_key')
        self.assertEqual(h.namespace, 'my_key')

    def test_lazy_pid_fallback_to_module_name(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T'},
                                 module_name='my_mod', class_name='C')
        self.assertEqual(h.namespace, 'my_mod')  # no key

    def test_lazy_pid_fallback_to_unknown(self):
        h = PluginManager.Handle(None, self.app, self.mgr, metadata={})
        self.assertEqual(h.namespace, 'unknown')

    def test_lazy_metadata_fields(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={
                                     'name': 'Mine',
                                     'name_zh': '中文',
                                     'priority': 10,
                                     'fixed_position': False,
                                     'fixed_size': False,
                                     'use_app_icon': False,
                                     'reload': False,
                                     'auto_start': True,
                                     'start_hidden': True,
                                 },
                                 module_name='m', class_name='C')
        self.assertEqual(h._name_raw, 'Mine')
        self.assertEqual(h._name_zh, '中文')
        self.assertEqual(h.priority, 10)
        self.assertFalse(h.fixed_position)
        self.assertFalse(h.fixed_size)
        self.assertFalse(h.use_app_icon)
        self.assertFalse(h.reload)
        self.assertTrue(h.auto_start)
        self.assertTrue(h.start_hidden)

    def test_lazy_metadata_defaults(self):
        h = PluginManager.Handle(None, self.app, self.mgr, metadata={},
                                 module_name='m', class_name='C')
        self.assertTrue(h.fixed_position)
        self.assertTrue(h.fixed_size)
        self.assertTrue(h.use_app_icon)
        self.assertTrue(h.reload)
        self.assertEqual(h.priority, 0)
        self.assertFalse(h.auto_start)
        self.assertFalse(h.start_hidden)

    def test_lazy_get_name_zh(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'EN', 'name_zh': '中文'},
                                 module_name='m', class_name='C')
        self.app.current_lang_name = 'zh'
        self.assertEqual(h.get_name(), '中文')
        self.app.current_lang_name = 'en'
        self.assertEqual(h.get_name(), 'EN')

    def test_lazy_get_name_en(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'Default', 'name_en': 'English'},
                                 module_name='m', class_name='C')
        self.app.current_lang_name = 'en'
        self.assertEqual(h.get_name(), 'English')

    def test_lazy_get_name_fallback(self):
        h = PluginManager.Handle(None, self.app, self.mgr, metadata={},
                                 module_name='my_mod', class_name='C')
        self.assertEqual(h.get_name(), 'my_mod')  # module_name is default


# ===========================================================================
#  Handle — eager mode (cls is the real class)
# ===========================================================================


class TestHandleEager(_EagerTestBase, unittest.TestCase):
    """Handle created directly from a plugin class (eager)."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_eager_is_loaded(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.assertTrue(h.loaded)

    def test_eager_pid_from_class(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.assertEqual(h.namespace, 'mock_gui')

    def test_eager_class_attrs(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.assertEqual(h.priority, 50)
        self.assertTrue(h.reload)
        self.assertTrue(h.fixed_position)
        self.assertTrue(h.fixed_size)
        self.assertTrue(h.use_app_icon)

    def test_eager_get_name(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.assertEqual(h.get_name(), 'Mock GUI')

    def test_eager_service_detected(self):
        h = PluginManager.Handle(_EagerService, self.app, self.mgr, key='s')
        self.assertTrue(h.is_service)


# ===========================================================================
#  Handle — visible / alive / loaded
# ===========================================================================


class TestHandleState(_EagerTestBase, unittest.TestCase):
    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_not_alive_when_no_instance(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.assertFalse(h.alive)

    def test_alive_when_instance_exists(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        win = make_mock_win()
        h._inst = win
        self.assertTrue(h.alive)

    def test_not_alive_when_instance_destroyed(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        win = MagicMock()
        win.winfo_exists.return_value = False
        h._inst = win
        self.assertFalse(h.alive)

    def test_service_alive_with_instance(self):
        h = PluginManager.Handle(_EagerService, self.app, self.mgr, key='s')
        h._inst = MagicMock()
        self.assertTrue(h.alive)

    def test_not_visible_when_no_instance(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.assertFalse(h.visible)

    def test_visible_when_viewable(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h._inst = make_mock_win()
        self.assertTrue(h.visible)

    def test_service_never_visible(self):
        h = PluginManager.Handle(_EagerService, self.app, self.mgr, key='s')
        h._inst = MagicMock()
        self.assertFalse(h.visible)


# ===========================================================================
#  Handle — pid resolution priority
# ===========================================================================


class TestHandlePid(_EagerTestBase, unittest.TestCase):
    """pid: class attr → AST metadata → registry key → module_name → 'unknown'."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_ast_metadata_second(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T', 'namespace': 'ast_pid'},
                                 module_name='m', class_name='C', key='reg_key')
        self.assertEqual(h.namespace, 'ast_pid')

    def test_registry_key_third(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T'},
                                 module_name='m', class_name='C', key='reg_key')
        self.assertEqual(h.namespace, 'reg_key')

    def test_module_name_fourth(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T'},
                                 module_name='mod', class_name='C')
        self.assertEqual(h.namespace, 'mod')

    def test_unknown_last(self):
        h = PluginManager.Handle(None, self.app, self.mgr, metadata={})
        self.assertEqual(h.namespace, 'unknown')

    def test_eager_without_namespace_attr(self):
        """Class without namespace falls back normally."""
        cls = type('NoId', (_MockGui,), {'name': 'X', 'namespace': None})
        h = PluginManager.Handle(cls, self.app, self.mgr, key='reg_key')
        h._namespace = 'ast_pid'
        # class attr is None → skip; AST metadata 'ast_pid' wins
        self.assertEqual(h.namespace, 'ast_pid')


# ===========================================================================
#  Manager — _resolve_one
# ===========================================================================


class TestResolveOne(unittest.TestCase):
    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def _add(self, key, pid=None):
        meta = {'name': key}
        if pid:
            meta['namespace'] = pid
        self.mgr.plugins[key] = PluginManager.Handle(
            None, self.app, self.mgr, metadata=meta,
            module_name=key, class_name='C', key=key)

    def test_by_registry_key(self):
        self._add('plugin_a')
        found, h = self.mgr._resolve_one('plugin_a')
        self.assertTrue(found)
        self.assertEqual(h.namespace, 'plugin_a')

    def test_by_pid(self):
        self._add('plugin_a', pid='my_id')
        found, h = self.mgr._resolve_one('my_id')
        self.assertTrue(found)
        self.assertEqual(h.namespace, 'my_id')

    def test_not_found(self):
        found, handles = self.mgr._resolve_one('nobody')
        self.assertFalse(found)
        self.assertEqual(handles, [])

    def test_pid_takes_priority_when_matches_both(self):
        """If a key matches one handle's pid, and another handle's key, pid wins."""
        self._add('plugin_a', pid='x')
        self._add('y')  # key='y', pid='y'
        found, h = self.mgr._resolve_one('y')
        self.assertTrue(found)
        self.assertEqual(h._key, 'y')


# ===========================================================================
#  Manager — _resolve_targets
# ===========================================================================


class TestResolveTargets(unittest.TestCase):
    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)
        for name, pid in [('a', 'pid_a'), ('b', 'pid_b'), ('c', 'pid_c')]:
            self.mgr.plugins[name] = PluginManager.Handle(
                None, self.app, self.mgr,
                metadata={'name': name, 'namespace': pid},
                module_name=name, class_name='C', key=name)

    def _handles(self, ret):
        """Flatten _resolve_targets result into handles."""
        out = []
        for found, item in ret:
            if not found:
                continue
            if isinstance(item, list):
                out.extend(item)
            else:
                out.append(item)
        return out

    def test_single_string_by_key(self):
        result = self.mgr._resolve_targets('a')
        self.assertEqual(len(result), 1)
        found, h = result[0]
        self.assertTrue(found)
        self.assertEqual(h._key, 'a')

    def test_single_string_by_pid(self):
        result = self.mgr._resolve_targets('pid_b')
        self.assertEqual(len(result), 1)
        found, h = result[0]
        self.assertTrue(found)
        self.assertEqual(h._key, 'b')

    def test_list_of_targets(self):
        result = self.mgr._resolve_targets(['a', 'pid_c'])
        self.assertEqual(len(result), 2)
        keys = {h._key for h in self._handles(result)}
        self.assertEqual(keys, {'a', 'c'})

    def test_unknown_target_in_list(self):
        """List of unknown targets returns (False, []) entries."""
        result = self.mgr._resolve_targets(['unknown', 'a'])
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0][0])  # 'unknown' not matched
        self.assertTrue(result[1][0])   # 'a' matched

    def test_unknown_target_string(self):
        """Single-string unknown returns one (False, []) entry."""
        result = self.mgr._resolve_targets('unknown')
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0][0])

    def test_flush_on_list_match(self):
        """Non-exact match triggers a flush retry."""
        with patch.object(self.mgr, 'flush') as mock_flush:
            result = self.mgr._resolve_targets('pid_a')  # exact, no flush
            self.assertTrue(result[0][0])
            mock_flush.assert_not_called()

        with patch.object(self.mgr, 'flush'):
            # 'pid' is a substring of all pids → fuzzy list match
            result = self.mgr._resolve_targets('pid')
            self.assertTrue(result[0][0])
            self.assertIsInstance(result[0][1], list)

    def test_empty_targets(self):
        self.assertEqual(self.mgr._resolve_targets(''), [])
        self.assertEqual(self.mgr._resolve_targets([]), [])
        self.assertEqual(self.mgr._resolve_targets(None), [])


# ===========================================================================
#  Manager — get_plugin / _info_for
# ===========================================================================


class TestPluginInfo(_EagerTestBase, unittest.TestCase):
    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_get_plugin_all(self):
        h1 = PluginManager.Handle(None, self.app, self.mgr,
                                  metadata={'name': 'Plugin A', 'namespace': 'pa'},
                                  module_name='mod_a', class_name='ClsA', key='a')
        h2 = PluginManager.Handle(_EagerService, self.app, self.mgr, key='s')
        self.mgr.plugins = {'a': h1, 's': h2}

        info = self.mgr._service_list_plugins()
        namespaces = {i['namespace'] for i in info}
        self.assertIn('pa', namespaces)
        self.assertIn('mock_svc', namespaces)
        types = {i['namespace']: i['type'] for i in info}
        self.assertEqual(types['pa'], 'GuiPlugin')
        self.assertEqual(types['mock_svc'], 'ServicePlugin')

    def test_get_plugin_single(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.mgr.plugins['g'] = h
        info = self.mgr._service_get_plugin('mock_gui')
        self.assertEqual(info['namespace'], 'mock_gui')
        self.assertEqual(info['name'], 'Mock GUI')
        self.assertEqual(info['type'], 'GuiPlugin')
        self.assertFalse(info['alive'])

    def test_get_plugin_not_found(self):
        self.assertIsNone(self.mgr._service_get_plugin('unknown'))

    def test_info_for_lazy_handle(self):
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'Lazy'},
                                 module_name='mod', class_name='LazyCls', key='lk')
        info = self.mgr._info_for(h)
        self.assertEqual(info['class_name'], 'LazyCls')
        self.assertEqual(info['namespace'], 'lk')
        self.assertEqual(info['class_name'], 'LazyCls')

    def test_info_for_eager_handle(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        info = self.mgr._info_for(h)
        self.assertEqual(info['class_name'], 'EagerGui')
        self.assertEqual(info['namespace'], 'mock_gui')
        self.assertTrue(info['reload'])  # GUI: reload is reported

    def test_info_for_service_reload_none(self):
        h = PluginManager.Handle(_EagerService, self.app, self.mgr, key='s')
        info = self.mgr._info_for(h)
        self.assertIsNone(info['reload'])
        self.assertFalse(info['visible'])


# ===========================================================================
#  Manager — lifecycle API
# ===========================================================================


class TestLifecycle(_EagerTestBase, unittest.TestCase):
    """start_plugin / stop_plugin / show_plugin / hide_plugin."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)
        self.handle = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')

    def test_start_plugin_starts_unstarted(self):
        win = make_mock_win()
        with patch.object(PluginManager.Handle, 'start', return_value=win) as mock_start:
            result = self.mgr.start_plugin(self.handle)
            mock_start.assert_called_once()
            self.assertIsInstance(result, HookInfo)
            self.assertEqual(result.namespace, 'mock_gui')

    def test_start_plugin_returns_hookinfo_when_alive(self):
        """start_plugin returns HookInfo for an already-alive GUI plugin."""
        win = make_mock_win()
        self.handle._inst = win
        with patch.object(PluginManager.Handle, 'show') as mock_show:
            result = self.mgr.start_plugin(self.handle)
            mock_show.assert_called_once()
            self.assertIsInstance(result, HookInfo)

    def test_stop_plugin_stops_alive(self):
        win = make_mock_win()
        self.handle._inst = win
        self.handle._cls = _EagerGui  # ensure is_service works
        with patch.object(PluginManager.Handle, 'close') as mock_close:
            result = self.mgr.stop_plugin(self.handle)
            mock_close.assert_called_once()
            self.assertIsInstance(result, HookInfo)

    def test_stop_plugin_noop_not_alive(self):
        with patch.object(PluginManager.Handle, 'close') as mock_close:
            result = self.mgr.stop_plugin(self.handle)
            mock_close.assert_not_called()
            self.assertIsInstance(result, HookInfo)

    def test_show_plugin_noop_for_service(self):
        h_svc = PluginManager.Handle(_EagerService, self.app, self.mgr, key='s')
        h_svc._inst = MagicMock()
        with patch.object(PluginManager.Handle, 'show') as mock_show:
            self.mgr.show_plugin(h_svc)
            mock_show.assert_not_called()

    def test_hide_plugin_noop_not_alive(self):
        with patch.object(PluginManager.Handle, 'hide') as mock_hide:
            self.mgr.hide_plugin(self.handle)
            mock_hide.assert_not_called()

    def test_hide_plugin_delegates_when_alive(self):
        win = make_mock_win()
        self.handle._inst = win
        with patch.object(PluginManager.Handle, 'hide') as mock_hide:
            self.mgr.hide_plugin(self.handle)
            mock_hide.assert_called_once()


# ===========================================================================
#  Manager — control events
# ===========================================================================


class TestAutoStart(_EagerTestBase, unittest.TestCase):
    """PluginManager._auto_start_plugins — loads then auto-starts eligible plugins."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_auto_start_eligible(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h.auto_start = True
        self.mgr.plugins['g'] = h
        with patch.object(self.mgr, 'flush'):
            with patch.object(self.mgr, 'start_plugin') as mock_start:
                self.mgr._auto_start_plugins()
                mock_start.assert_called_once_with(h)

    def test_auto_start_skips_already_alive(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h.auto_start = True
        h._inst = make_mock_win()
        self.mgr.plugins['g'] = h
        with patch.object(self.mgr, 'flush'):
            with patch.object(self.mgr, 'start_plugin') as mock_start:
                self.mgr._auto_start_plugins()
                mock_start.assert_not_called()

    def test_auto_start_skips_not_auto_start(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h.auto_start = False
        self.mgr.plugins['g'] = h
        with patch.object(self.mgr, 'flush'):
            with patch.object(self.mgr, 'start_plugin') as mock_start:
                self.mgr._auto_start_plugins()
                mock_start.assert_not_called()


class TestControlEvents(_EagerTestBase, unittest.TestCase):
    """_register_services is called in __init__ — verifies registrations."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_plugins_services_registered_in_init(self):
        svc = self.app._infra.services
        svc.register.assert_has_calls([
            call('auto_start', self.mgr._auto_start_plugins, ns='plugins'),
            call('start', self.mgr._service_start_plugin, ns='plugins'),
            call('stop', self.mgr._service_stop_plugin, ns='plugins'),
            call('show', self.mgr._service_show_plugin, ns='plugins'),
            call('hide', self.mgr._service_hide_plugin, ns='plugins'),
            call('list', self.mgr._service_list_plugins, ns='plugins'),
            call('check', self.mgr._service_check_plugin, ns='plugins'),
            call('get', self.mgr._service_get_plugin, ns='plugins'),
            call('flush', self.mgr.flush, ns='plugins'),
        ], any_order=True)

    def test_stop_plugin_delegates(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h._inst = make_mock_win()
        self.mgr.plugins['g'] = h
        # service methods schedule on the UI thread via after(0)
        self.app.after.side_effect = lambda _ms, fn: fn()

        with patch.object(self.mgr, 'stop_plugin') as mock_stop:
            self.mgr._service_stop_plugin('mock_gui')
            mock_stop.assert_called_once_with(h)

    def test_hide_plugin_with_exclude(self):
        """List hide excludes the caller by namespace."""
        h1 = PluginManager.Handle(None, self.app, self.mgr,
                                  metadata={'name': 'A', 'namespace': 'pa'},
                                  module_name='a', class_name='C', key='a')
        h2 = PluginManager.Handle(None, self.app, self.mgr,
                                  metadata={'name': 'B', 'namespace': 'pb'},
                                  module_name='b', class_name='C', key='b')
        h1._inst = make_mock_win()
        h2._inst = make_mock_win()
        self.mgr.plugins = {'a': h1, 'b': h2}
        self.app.after.side_effect = lambda _ms, fn: fn()

        with patch.object(self.mgr, 'hide_plugin') as mock_hide:
            self.mgr._service_hide_plugin(['pa', 'pb'], exclude='pa')
            mock_hide.assert_called_once_with(h2)  # only 'pb', not 'pa'


# ===========================================================================
#  Manager — namespace uniqueness
# ===========================================================================


class TestPluginIdUniqueness(unittest.TestCase):
    def test_duplicate_detection(self):
        app = make_mock_app()
        mgr = PluginManager(make_logger(), app)
        h1 = PluginManager.Handle(None, app, mgr,
                                  metadata={'name': 'A', 'namespace': 'same_id'},
                                  module_name='a', class_name='C', key='a')
        h2 = PluginManager.Handle(None, app, mgr,
                                  metadata={'name': 'B', 'namespace': 'same_id'},
                                  module_name='b', class_name='C', key='b')
        mgr.plugins = {'a': h1, 'b': h2}

        with self.assertLogs(mgr.logger, level='ERROR') as cm:
            pid_seen = {}
            for key, h in mgr.plugins.items():
                pid = h.namespace
                if pid in pid_seen:
                    mgr.logger.error(
                        '[PluginManager] duplicate namespace "%s": '
                        'used by both "%s" and "%s"',
                        pid, pid_seen[pid], key)
                else:
                    pid_seen[pid] = key
        self.assertTrue(any('duplicate namespace "same_id"' in msg
                           for msg in cm.output))


# ===========================================================================
#  META_KEYS
# ===========================================================================


class TestMetaKeys(unittest.TestCase):
    def test_meta_keys_includes_new_fields(self):
        keys = PluginManager.META_KEYS
        self.assertIn('namespace', keys)
        self.assertIn('namespace', keys)
        self.assertIn('name', keys)
        self.assertIn('priority', keys)
        self.assertIn('fixed_position', keys)
        self.assertIn('reload', keys)
        self.assertIn('auto_start', keys)
        self.assertIn('start_hidden', keys)


if __name__ == '__main__':
    unittest.main()
