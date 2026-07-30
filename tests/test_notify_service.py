# -*- coding: utf-8 -*-
"""Unit tests for NotifyService — pure logic, no tkinter window creation."""
import unittest

from plugins.task_scheduler.notify_service import (
    NotifyService,
    _NotifyBase,
    _Toast,
    _Banner,
    _Popup,
    _Canvas,
)


# ---------------------------------------------------------------------------
# _i — int conversion
# ---------------------------------------------------------------------------

class TestIntConversion(unittest.TestCase):

    def test_int_returns_int(self):
        self.assertEqual(_NotifyBase._i(42), 42)

    def test_float_truncated(self):
        self.assertEqual(_NotifyBase._i(3.14), 3)

    def test_digit_string(self):
        self.assertEqual(_NotifyBase._i('42'), 42)

    def test_stripped_digit_string(self):
        self.assertEqual(_NotifyBase._i('  42  '), 42)

    def test_none_returns_default(self):
        self.assertEqual(_NotifyBase._i(None, 99), 99)

    def test_empty_string_returns_default(self):
        self.assertEqual(_NotifyBase._i('', 99), 99)

    def test_whitespace_string_returns_default(self):
        self.assertEqual(_NotifyBase._i('   ', 99), 99)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            _NotifyBase._i('abc')

    def test_zero_is_valid(self):
        self.assertEqual(_NotifyBase._i(0), 0)

    def test_zero_string_is_valid(self):
        self.assertEqual(_NotifyBase._i('0'), 0)

    def test_default_default_is_zero(self):
        self.assertEqual(_NotifyBase._i(None), 0)


# ---------------------------------------------------------------------------
# NotifyService — registration & attributes
# ---------------------------------------------------------------------------

class TestNotifyServiceAttrs(unittest.TestCase):

    def test_namespace(self):
        self.assertEqual(NotifyService.namespace, 'notify')

    def test_name(self):
        self.assertEqual(NotifyService.name, 'Notifications')

    def test_name_zh(self):
        self.assertEqual(NotifyService.name_zh, '通知服务')

    def test_style_mapping(self):
        self.assertIs(NotifyService._STYLES['toast'], _Toast)
        self.assertIs(NotifyService._STYLES['popup'], _Popup)
        self.assertIs(NotifyService._STYLES['banner'], _Banner)
        self.assertIs(NotifyService._STYLES['canvas'], _Canvas)

    def test_all_styles_have_classes(self):
        for style in ('toast', 'popup', 'banner', 'canvas'):
            self.assertIn(style, NotifyService._STYLES)
            self.assertTrue(callable(NotifyService._STYLES[style]))


# ---------------------------------------------------------------------------
# _Canvas — pattern validation
# ---------------------------------------------------------------------------

class TestCanvasPatterns(unittest.TestCase):

    def test_valid_patterns(self):
        for p in ('flower', 'heart', 'star', 'sun', 'smiley'):
            self.assertIn(p, _Canvas._PATTERNS)

    def test_all_patterns_have_titles(self):
        for p in _Canvas._PATTERNS:
            self.assertIn(p, _Canvas._TITLES)
            self.assertTrue(len(_Canvas._TITLES[p]) > 0)

    def test_all_patterns_have_sizes(self):
        for p in _Canvas._PATTERNS:
            self.assertIn(p, _Canvas._SIZES)
            w, h = _Canvas._SIZES[p]
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)

    def test_flower_is_default_pattern(self):
        self.assertIn('flower', _Canvas._PATTERNS)

    def test_flower_tallest(self):
        """Flower should be taller than other patterns (has stem)."""
        fh = _Canvas._SIZES['flower'][1]
        for p in _Canvas._PATTERNS:
            if p != 'flower':
                self.assertGreaterEqual(fh, _Canvas._SIZES[p][1])


# ---------------------------------------------------------------------------
# _Toast — position mapping
# ---------------------------------------------------------------------------

class TestToastPosition(unittest.TestCase):

    def test_position_keys(self):
        for p in ('tl', 'tr', 'bl', 'br'):
            self.assertIn(p, _Toast._POS)

    def test_br_is_right_bottom(self):
        rx, ry, start_dir, _ = _Toast._POS['br']
        self.assertEqual(rx, 1.0)
        self.assertEqual(ry, 1.0)
        self.assertEqual(start_dir, 's')

    def test_tl_is_left_top(self):
        rx, ry, start_dir, _ = _Toast._POS['tl']
        self.assertEqual(rx, 0.0)
        self.assertEqual(ry, 0.0)
        self.assertEqual(start_dir, 'n')

    def test_bl_is_left_bottom(self):
        rx, ry, start_dir, _ = _Toast._POS['bl']
        self.assertEqual(rx, 0.0)
        self.assertEqual(ry, 1.0)
        self.assertEqual(start_dir, 's')

    def test_tr_is_right_top(self):
        rx, ry, start_dir, _ = _Toast._POS['tr']
        self.assertEqual(rx, 1.0)
        self.assertEqual(ry, 0.0)
        self.assertEqual(start_dir, 'n')


# ---------------------------------------------------------------------------
# Combined test run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main()
