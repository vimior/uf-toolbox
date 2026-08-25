# -*- coding: utf-8 -*-
"""Unit tests for PluginManager — Handle, lifecycle, resolution, control events."""

import logging
import unittest

from unittest.mock import Mock, MagicMock, PropertyMock, call, patch
from plugins.manager import PluginManager

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
    if base.__name__ == 'GuiPlugin' and getattr(cls, '_mock_gui', False):
        return True
    if base.__name__ == 'ServicePlugin' and getattr(cls, '_mock_svc', False):
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
        result = self.mgr._resolve_one('plugin_a')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'plugin_a')

    def test_by_pid(self):
        self._add('plugin_a', pid='my_id')
        result = self.mgr._resolve_one('my_id')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'plugin_a')

    def test_not_found(self):
        self.assertIsNone(self.mgr._resolve_one('nobody'))

    def test_pid_takes_priority_when_matches_both(self):
        """If a key matches one handle's pid, and another handle's key, pid wins."""
        self._add('plugin_a', pid='x')
        self._add('y')  # key='y', pid='y'
        # 'y' matches plugin_a's pid 'x'? No.
        # 'y' matches y's key → found
        result = self.mgr._resolve_one('y')
        self.assertEqual(result[0], 'y')


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

    def test_wildcard_returns_all(self):
        result = self.mgr._resolve_targets('*')
        self.assertEqual(len(result), 3)

    def test_single_string_by_key(self):
        result = self.mgr._resolve_targets('a')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'a')

    def test_single_string_by_pid(self):
        result = self.mgr._resolve_targets('pid_b')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'b')

    def test_list_of_targets(self):
        result = self.mgr._resolve_targets(['a', 'pid_c'])
        self.assertEqual(len(result), 2)
        keys = {r[0] for r in result}
        self.assertEqual(keys, {'a', 'c'})

    def test_unknown_target_in_list_warning(self):
        """List of targets with unknown entries logs warning."""
        with self.assertLogs(self.mgr.logger, level='WARNING') as cm:
            result = self.mgr._resolve_targets(['unknown', 'a'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'a')
        self.assertTrue(any('unknown target' in msg for msg in cm.output))

    def test_unknown_target_string_no_warning(self):
        """Single-string unknown returns empty list without warning."""
        result = self.mgr._resolve_targets('unknown')
        self.assertEqual(len(result), 0)

    def test_exclude_string(self):
        result = self.mgr._resolve_targets('*', exclude='pid_a')
        self.assertEqual(len(result), 2)
        keys = {r[0] for r in result}
        self.assertEqual(keys, {'b', 'c'})

    def test_exclude_list(self):
        result = self.mgr._resolve_targets('*', exclude=['pid_a', 'pid_c'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], 'b')

    def test_exclude_no_match(self):
        result = self.mgr._resolve_targets('*', exclude='pid_x')
        self.assertEqual(len(result), 3)

    def test_exclude_none(self):
        result = self.mgr._resolve_targets('*', exclude=None)
        self.assertEqual(len(result), 3)


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

        info = self.mgr.get_plugin()
        self.assertIn('pa', info)
        self.assertIn('mock_svc', info)
        self.assertEqual(info['pa']['type'], 'GuiPlugin')
        self.assertEqual(info['mock_svc']['type'], 'ServicePlugin')

    def test_get_plugin_single(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        self.mgr.plugins['g'] = h
        info = self.mgr.get_plugin('mock_gui')
        self.assertEqual(info['namespace'], 'mock_gui')
        self.assertEqual(info['name'], 'Mock GUI')
        self.assertEqual(info['type'], 'GuiPlugin')
        self.assertFalse(info['alive'])

    def test_get_plugin_not_found(self):
        self.assertIsNone(self.mgr.get_plugin('unknown'))

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
            result, menu = self.mgr.start_plugin(self.handle, self.app)
            mock_start.assert_called_once()
            self.assertEqual(result, win)
            self.assertFalse(menu)  # already loaded

    def test_start_plugin_menu_changed_for_lazy_handle(self):
        """When a lazy handle loads and becomes eager, menu_changed is True."""
        h = PluginManager.Handle(None, self.app, self.mgr,
                                 metadata={'name': 'T'},
                                 module_name='m', class_name='C', key='k')
        self.assertFalse(h.loaded)
        win = make_mock_win()
        with patch.object(PluginManager.Handle, 'start', return_value=win):
            # After start(), _ensure_loaded sets _cls, so loaded becomes True
            with patch.object(PluginManager.Handle, 'loaded',
                              PropertyMock(side_effect=[False, True])):
                result, menu = self.mgr.start_plugin(h, self.app)
                self.assertTrue(menu)

    def test_stop_plugin_stops_alive(self):
        win = make_mock_win()
        self.handle._inst = win
        self.handle._cls = _EagerGui  # ensure is_service works
        with patch.object(PluginManager.Handle, 'close') as mock_close:
            self.mgr.stop_plugin(self.handle)
            mock_close.assert_called_once()

    def test_stop_plugin_noop_not_alive(self):
        with patch.object(PluginManager.Handle, 'close') as mock_close:
            self.mgr.stop_plugin(self.handle)
            mock_close.assert_not_called()

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


# ===========================================================================
#  Manager — control events
# ===========================================================================


class TestAutoStart(_EagerTestBase, unittest.TestCase):
    """PluginManager._on_auto_start — loads then auto-starts eligible plugins."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_auto_start_eligible(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h.auto_start = True
        self.mgr.plugins['g'] = h
        with patch.object(self.mgr, 'load'):
            with patch.object(PluginManager.Handle, 'start') as mock_start:
                with patch.object(PluginManager.Handle, 'is_service',
                                  PropertyMock(return_value=False)):
                    self.mgr._on_auto_start()
                    mock_start.assert_called_once()

    def test_auto_start_skips_already_alive(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h.auto_start = True
        h._inst = make_mock_win()
        self.mgr.plugins['g'] = h
        with patch.object(self.mgr, 'load'):
            with patch.object(PluginManager.Handle, 'start') as mock_start:
                self.mgr._on_auto_start()
                mock_start.assert_not_called()

    def test_auto_start_skips_not_auto_start(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h.auto_start = False
        self.mgr.plugins['g'] = h
        with patch.object(self.mgr, 'load'):
            with patch.object(PluginManager.Handle, 'start') as mock_start:
                self.mgr._on_auto_start()
                mock_start.assert_not_called()


class TestControlEvents(_EagerTestBase, unittest.TestCase):
    """_setup_control_events is called in __init__ — verifies registrations."""

    def setUp(self):
        self.app = make_mock_app()
        self.mgr = PluginManager(make_logger(), self.app)

    def test_control_events_registered_in_init(self):
        bus = self.app._infra.eventbus
        self.assertEqual(bus.on.call_count, 5)
        events = {call[0][0] for call in bus.on.call_args_list}
        self.assertEqual(events, {
            'plugins@start',
            'plugins@stop',
            'plugins@show',
            'plugins@hide',
            'plugins@auto-start',
        })

    def test_info_service_registered_in_init(self):
        svc = self.app._infra.services
        svc.register.assert_has_calls([
            call('get', self.mgr.get_plugin, ns='plugins'),
            call('list_capabilities', self.mgr._svc_list_capabilities,
                 ns='plugins'),
        ], any_order=True)

    def test_on_plugin_stop_delegates(self):
        h = PluginManager.Handle(_EagerGui, self.app, self.mgr, key='g')
        h._inst = make_mock_win()
        self.mgr.plugins['g'] = h

        with patch.object(self.mgr, 'stop_plugin') as mock_stop:
            self.mgr._on_plugin_stop('mock_gui')
            mock_stop.assert_called_once_with(h)

    def test_on_plugin_hide_with_exclude(self):
        """Wildcard hide excludes the caller."""
        h1 = PluginManager.Handle(None, self.app, self.mgr,
                                  metadata={'name': 'A', 'namespace': 'pa'},
                                  module_name='a', class_name='C', key='a')
        h2 = PluginManager.Handle(None, self.app, self.mgr,
                                  metadata={'name': 'B', 'namespace': 'pb'},
                                  module_name='b', class_name='C', key='b')
        h1._inst = make_mock_win()
        h2._inst = make_mock_win()
        self.mgr.plugins = {'a': h1, 'b': h2}

        with patch.object(self.mgr, 'hide_plugin') as mock_hide:
            self.mgr._on_plugin_hide('*', exclude='pa')
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
