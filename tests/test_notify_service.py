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
    _STACK_GAP,
    _MAX_STACK,
    _MAX_STACK_RATIO,
    _work_area,
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
# constants
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_stack_gap(self):
        self.assertEqual(_STACK_GAP, 2)

    def test_max_stack(self):
        self.assertEqual(_MAX_STACK, 10)

    def test_max_stack_ratio(self):
        self.assertEqual(_MAX_STACK_RATIO, 0.6)

    def test_wakeup_event(self):
        self.assertEqual(NotifyService._WAKEUP_EVENT, '<<NotifyPoll>>')

    def test_style_defaults_present(self):
        """Each style class defines its own class-level style defaults."""
        for cls in (_Toast, _Banner, _Popup, _Canvas):
            self.assertTrue(hasattr(cls, '_DEF_BG'))
            self.assertTrue(hasattr(cls, '_DEF_FG'))
            self.assertTrue(hasattr(cls, '_DEF_FONT_SIZE'))
            self.assertTrue(hasattr(cls, '_DEF_TIME_FONT_SIZE'))


# ---------------------------------------------------------------------------
# _parse_show_time
# ---------------------------------------------------------------------------

class TestParseShowTime(unittest.TestCase):

    def test_true_values(self):
        for v in (True, 1, '1', 'True', 'true', 'yes', None):
            self.assertTrue(_NotifyBase._parse_show_time(v), repr(v))

    def test_false_values(self):
        for v in (False, 0, '0', 'False', 'false', ''):
            self.assertFalse(_NotifyBase._parse_show_time(v), repr(v))


# ---------------------------------------------------------------------------
# _work_area (non-Windows fallback)
# ---------------------------------------------------------------------------

class TestWorkArea(unittest.TestCase):

    def test_non_win32_falls_back_to_screen(self):
        import sys
        if sys.platform == 'win32':
            self.skipTest('running on Windows')
        root = type('R', (), {
            'winfo_screenwidth': lambda self: 1920,
            'winfo_screenheight': lambda self: 1080,
        })()
        self.assertEqual(_work_area(root), (0, 0, 1920, 1080))


# ---------------------------------------------------------------------------
# _reflow — mock windows (no tkinter)
# ---------------------------------------------------------------------------

class _MockWin:
    """Minimal stand-in for a stackable notification window."""

    def __init__(self, h, base_y=0, position=None, free=False):
        self._h = h
        self._base_y = base_y
        self._target_y = base_y
        self._position = position
        self._free_placed = free
        self._alive = True
        self._owner = None
        self.placed = []  # 记录 _place_at 调用

    def winfo_exists(self):
        return self._alive

    def winfo_height(self):
        return self._h

    def _place_at(self, y):
        self.placed.append(y)
        self._target_y = y

    def destroy(self):
        """模拟真实 destroy → owner._popup_closed 清理引用."""
        self._alive = False
        if self._owner is not None:
            self._owner._popup_closed(self)


def _mk_svc():
    svc = NotifyService.__new__(NotifyService)
    svc.root = None  # reflow 跳过 update_idletasks / 屏幕判断
    svc._popups = {}
    svc._unique_windows = []
    return svc


class TestReflow(unittest.TestCase):

    def test_unique_alone_moves_to_base(self):
        """唯一窗口归位基准 (复用消失后 unique 回顶部/角落)."""
        svc = _mk_svc()
        w = _MockWin(60, base_y=100, position='br')
        w._target_y = 160  # 当前在偏移位
        w._notify_style = 'toast'
        svc._unique_windows.append(w)
        svc._reflow('toast')
        self.assertEqual(w._target_y, 100)
        self.assertEqual(w.placed, [100])

    def test_upward_stack_uses_own_height(self):
        """底部角落向上堆: 新窗口底部贴前窗口顶部 → 用自己高度."""
        svc = _mk_svc()
        reuse = _MockWin(80, base_y=900, position='br')
        reuse._notify_style = 'toast'
        reuse._popup_key = 'toast:br'
        svc._popups[reuse._popup_key] = reuse
        uni = _MockWin(60, base_y=900, position='br')
        uni._notify_style = 'toast'
        svc._unique_windows.append(uni)
        svc._reflow('toast')
        # uni 顶部 = 复用顶部 - uni高 - gap → 底部贴复用顶部
        self.assertEqual(uni._target_y, 900 - 60 - _STACK_GAP)
        self.assertEqual(reuse._target_y, 900)  # 复用恒基准位

    def test_downward_stack_uses_prev_height(self):
        """顶部角落向下堆: 新窗口顶部贴前窗口底部 → 用前窗口高度."""
        svc = _mk_svc()
        reuse = _MockWin(80, base_y=0, position='tr')  # 高复用
        reuse._notify_style = 'toast'
        reuse._popup_key = 'toast:tr'
        svc._popups[reuse._popup_key] = reuse
        uni = _MockWin(60, base_y=0, position='tr')    # 矮 unique
        uni._notify_style = 'toast'
        svc._unique_windows.append(uni)
        svc._reflow('toast')
        # uni 顶部 = 复用底部 (0+80) + gap → 用前窗口(复用)高度
        self.assertEqual(uni._target_y, 0 + 80 + _STACK_GAP)

    def test_different_positions_are_separate_chains(self):
        """不同 position 各自成链, 互不干扰."""
        svc = _mk_svc()
        br_reuse = _MockWin(80, base_y=900, position='br')
        br_reuse._notify_style = 'toast'
        br_reuse._popup_key = 'toast:br'
        svc._popups[br_reuse._popup_key] = br_reuse
        br_uni = _MockWin(60, base_y=900, position='br')
        br_uni._notify_style = 'toast'
        svc._unique_windows.append(br_uni)
        tr_uni = _MockWin(60, base_y=0, position='tr')
        tr_uni._notify_style = 'toast'
        svc._unique_windows.append(tr_uni)
        svc._reflow('toast')
        self.assertEqual(br_uni._target_y, 900 - 60 - _STACK_GAP)
        self.assertEqual(tr_uni._target_y, 0)  # tr 链只有自己 → 基准位

    def test_free_placed_excluded(self):
        """绝对定位 (x/y) 窗口不参与重排."""
        svc = _mk_svc()
        reuse = _MockWin(80, base_y=900, position='br')
        reuse._notify_style = 'toast'
        reuse._popup_key = 'toast:br'
        svc._popups[reuse._popup_key] = reuse
        free = _MockWin(60, base_y=300, position='br', free=True)
        free._notify_style = 'toast'
        svc._unique_windows.append(free)
        svc._reflow('toast')
        self.assertEqual(free.placed, [])  # 未被移动
        self.assertEqual(free._target_y, 300)

    def test_non_stackable_excluded(self):
        """popup/canvas (无 _place_at) 不参与重排, 不抛异常."""
        svc = _mk_svc()
        plain = type('P', (), {
            '_notify_style': 'canvas',
            '_free_placed': False,
            'winfo_exists': lambda self: True,
        })()  # 无 _place_at 的窗口
        svc._unique_windows.append(plain)
        svc._reflow('canvas')  # 不应抛 AttributeError
        self.assertTrue(True)

    def test_reflow_empty(self):
        svc = _mk_svc()
        svc._reflow('toast')  # 无窗口不抛异常
        self.assertTrue(True)


# ---------------------------------------------------------------------------
# _show_unique — eviction (数量/高度限制)
# ---------------------------------------------------------------------------

class TestShowUniqueEviction(unittest.TestCase):

    def _mk_svc(self):
        svc = NotifyService.__new__(NotifyService)
        svc.root = type('R', (), {
            'winfo_screenheight': lambda self: 1000,
            'update_idletasks': lambda self: None,
        })()
        svc._popups = {}
        svc._unique_windows = []
        svc.app = type('A', (), {'emit': lambda self, *a, **k: None})()
        return svc

    def _mk_toast_factory(self, h):
        def _factory(owner, text, **kw):
            w = _MockWin(h, base_y=900, position='br')
            w._owner = owner
            w._notify_style = 'toast'
            return w
        return _factory

    def test_evicts_oldest_when_over_max_stack(self):
        svc = self._mk_svc()
        svc._STYLES = {'toast': self._mk_toast_factory(60)}
        # 已存在 _MAX_STACK 个
        for i in range(_MAX_STACK):
            w = _MockWin(60, base_y=900, position='br')
            w._owner = svc
            w._notify_style = 'toast'
            svc._unique_windows.append(w)
        first = svc._unique_windows[0]
        svc._show_unique('toast', 'x', {})
        self.assertLessEqual(len(svc._unique_windows), _MAX_STACK)
        self.assertNotIn(first, svc._unique_windows)  # 最旧被淘汰

    def test_evicts_when_height_over_ratio(self):
        svc = self._mk_svc()
        svc._STYLES = {'toast': self._mk_toast_factory(100)}
        # 7 个 × 100 = 700 > 600 → 创建新窗口时淘汰最旧
        for i in range(7):
            w = _MockWin(100, base_y=900, position='br')
            w._owner = svc
            w._notify_style = 'toast'
            svc._unique_windows.append(w)
        first = svc._unique_windows[0]
        svc._show_unique('toast', 'x', {})
        self.assertNotIn(first, svc._unique_windows)  # 高度超限淘汰最旧
        # 复用窗口高度也计入: 复用 100 + 6 unique = 700 > 600 → 淘汰
        svc._unique_windows.clear()
        reuse = _MockWin(100, base_y=900, position='br')
        reuse._owner = svc
        reuse._notify_style = 'toast'
        reuse._popup_key = 'toast:br'
        svc._popups[reuse._popup_key] = reuse
        for i in range(6):
            w = _MockWin(100, base_y=900, position='br')
            w._owner = svc
            w._notify_style = 'toast'
            svc._unique_windows.append(w)
        before = list(svc._unique_windows)
        svc._show_unique('toast', 'x', {})
        self.assertNotIn(before[0], svc._unique_windows)


# ---------------------------------------------------------------------------
# _show_main — 复用窗口按 style+position 分键
# ---------------------------------------------------------------------------

class TestShowMainKeying(unittest.TestCase):

    def _mk_svc(self):
        svc = NotifyService.__new__(NotifyService)
        svc.root = None
        svc._popups = {}
        svc._unique_windows = []
        svc.app = type('A', (), {'emit': lambda self, *a, **k: None})()
        return svc

    def test_key_includes_position(self):
        svc = self._mk_svc()
        created = []

        class _FakeToast(_MockWin):
            def __init__(self, owner, text, **kw):
                super().__init__(60, base_y=900, position=kw.get('position'))
                created.append(kw.get('position'))

        svc._STYLES = {'toast': _FakeToast}
        svc._show_main('toast', 'a', {'position': 'br'})
        key = next(iter(svc._popups))
        self.assertEqual(key, 'toast:br')
        svc._show_main('toast', 'b', {'position': 'tr'})
        self.assertIn('toast:tr', svc._popups)
        self.assertEqual(len(svc._popups), 2)  # br/tr 各一个, 不互顶
        self.assertEqual(created, ['br', 'tr'])

    def test_refresh_hits_same_key(self):
        svc = self._mk_svc()
        refreshed = []

        class _FakeToast(_MockWin):
            def __init__(self, owner, text, **kw):
                super().__init__(60, base_y=900, position=kw.get('position'))
            def refresh(self, text, **kw):
                refreshed.append(text)

        svc._STYLES = {'toast': _FakeToast}
        svc._show_main('toast', 'a', {'position': 'br'})
        svc._show_main('toast', 'b', {'position': 'br'})  # 同 key → 刷新
        self.assertEqual(refreshed, ['b'])
        self.assertEqual(len(svc._popups), 1)


# ---------------------------------------------------------------------------
# Combined test run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main()
