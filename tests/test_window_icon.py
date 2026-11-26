# -*- coding: utf-8 -*-
"""Unit tests for window icon handling (shared HICON on Windows).

The regression this guards: calling ``wm iconbitmap`` per window leaks
~18 GDI + ~6 USER handles on Windows.  The fix loads each icon size once
and reuses the HICON via WM_SETICON.
"""
import ctypes
import os
import sys
import tkinter as tk
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import uf_toolbox


class FakeUser32:
    """Minimal user32 stand-in for the ctypes calls in uf_toolbox."""

    def __init__(self, load_result=0x1234):
        self.LoadImageW = MagicMock(return_value=load_result)
        self.SendMessageW = MagicMock(return_value=1)
        self.GetSystemMetrics = MagicMock(
            side_effect=lambda metric: 16 if metric in (49, 50) else 32)


def make_win(frame='0x1234'):
    win = MagicMock()
    win.wm_frame.return_value = frame
    win.winfo_id.return_value = 0x5678
    return win


class TestWinIconCache(unittest.TestCase):

    def setUp(self):
        uf_toolbox._WIN_ICONS.clear()

    def tearDown(self):
        uf_toolbox._WIN_ICONS.clear()

    def test_loads_once_per_size(self):
        fake = FakeUser32()
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            first = uf_toolbox._win_hicon('C:/icons/app.ico', 16, 16)
            second = uf_toolbox._win_hicon('C:/icons/app.ico', 16, 16)
        self.assertEqual(first, 0x1234)
        self.assertEqual(second, 0x1234)
        self.assertEqual(fake.LoadImageW.call_count, 1)

    def test_invalid_size_or_path_skips_load(self):
        fake = FakeUser32()
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            self.assertIsNone(uf_toolbox._win_hicon('', 16, 16))
            self.assertIsNone(uf_toolbox._win_hicon('C:/app.ico', 0, 16))
            self.assertIsNone(uf_toolbox._win_hicon('C:/app.ico', 16, 0))
        fake.LoadImageW.assert_not_called()

    def test_many_windows_share_two_hicons(self):
        """10 windows only load the small + big HICON once each."""
        fake = FakeUser32()
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            for _ in range(10):
                uf_toolbox._apply_win_icon(make_win(), 'C:/icons/app.ico')
        self.assertEqual(fake.LoadImageW.call_count, 2)
        self.assertEqual(fake.SendMessageW.call_count, 20)
        self.assertEqual(len(uf_toolbox._WIN_ICONS), 2)

    def test_reapply_is_idempotent(self):
        fake = FakeUser32()
        win = make_win()
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            uf_toolbox._apply_win_icon(win, 'C:/icons/app.ico')
            uf_toolbox._apply_win_icon(win, 'C:/icons/app.ico')
        self.assertEqual(fake.LoadImageW.call_count, 2)
        self.assertEqual(fake.SendMessageW.call_count, 4)


class TestApplyWinIcon(unittest.TestCase):

    def setUp(self):
        uf_toolbox._WIN_ICONS.clear()

    def tearDown(self):
        uf_toolbox._WIN_ICONS.clear()

    def test_falls_back_to_winfo_id(self):
        fake = FakeUser32()
        win = make_win(frame='.')
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            uf_toolbox._apply_win_icon(win, 'C:/icons/app.ico')
        self.assertTrue(fake.SendMessageW.called)

    def test_zero_handle_skips(self):
        fake = FakeUser32()
        win = make_win(frame='0x0')
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            uf_toolbox._apply_win_icon(win, 'C:/icons/app.ico')
        fake.SendMessageW.assert_not_called()

    def test_missing_icon_file_is_silent(self):
        fake = FakeUser32(load_result=0)
        with patch('ctypes.WinDLL', return_value=fake, create=True):
            uf_toolbox._apply_win_icon(make_win(), 'C:/missing.ico')
        fake.SendMessageW.assert_not_called()


class TestSetWindowIcon(unittest.TestCase):

    def setUp(self):
        uf_toolbox._WIN_ICONS.clear()

    def tearDown(self):
        uf_toolbox._WIN_ICONS.clear()

    def test_windows_does_not_call_iconbitmap(self):
        owner = SimpleNamespace(ico_path='C:/icons/app.ico',
                                png_path='C:/icons/app.png', _icon=None)
        win = make_win()
        with patch.object(uf_toolbox.sys, 'platform', 'win32'), \
                patch.object(uf_toolbox, '_apply_win_icon') as apply:
            uf_toolbox.UFToolBox._set_window_icon(owner, win)
        apply.assert_called_once_with(win, 'C:/icons/app.ico')
        win.iconbitmap.assert_not_called()

    def test_non_windows_pil_fallback_keeps_reference(self):
        owner = SimpleNamespace(ico_path='C:/icons/app.ico',
                                png_path='C:/icons/app.png', _icon=None)
        win = make_win()

        fake_pil = types.ModuleType('PIL')
        fake_image = types.ModuleType('PIL.Image')
        fake_imagetk = types.ModuleType('PIL.ImageTk')
        fake_image.open = MagicMock(return_value=object())
        fake_imagetk.PhotoImage = MagicMock(return_value='photo')
        fake_pil.Image = fake_image
        fake_pil.ImageTk = fake_imagetk

        with patch.object(uf_toolbox.sys, 'platform', 'linux'), \
                patch.object(uf_toolbox.tk, 'PhotoImage',
                             side_effect=tk.TclError('no png support')), \
                patch.dict(sys.modules, {
                    'PIL': fake_pil,
                    'PIL.Image': fake_image,
                    'PIL.ImageTk': fake_imagetk,
                }):
            uf_toolbox.UFToolBox._set_window_icon(owner, win)

        self.assertEqual(owner._icon, 'photo')
        win.iconphoto.assert_called_once_with(True, 'photo')
        self.assertEqual(win._icon_ref, 'photo')


@unittest.skipUnless(
    sys.platform == 'win32' and os.environ.get('UF_TOOLBOX_HANDLE_TEST') == '1',
    'Windows handle test — set UF_TOOLBOX_HANDLE_TEST=1 to enable')
class TestWindowsHandleStability(unittest.TestCase):
    """Opt-in integration check: creating windows must not grow GDI/USER."""

    @staticmethod
    def _resources():
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        u32 = ctypes.WinDLL('user32', use_last_error=True)
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        u32.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        u32.GetGuiResources.restype = ctypes.c_uint
        h = k32.GetCurrentProcess()
        return (u32.GetGuiResources(h, 0), u32.GetGuiResources(h, 1))

    def test_gdi_user_handles_stay_stable(self):
        ico = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'icons', 'uf_toolbox.ico')
        try:
            root = tk.Tk()
        except tk.TclError as e:
            self.skipTest('no desktop: %s' % e)
        root.withdraw()
        uf_toolbox._WIN_ICONS.clear()
        try:
            def cycle(n):
                for _ in range(n):
                    win = tk.Toplevel(root)
                    win.withdraw()
                    uf_toolbox._apply_win_icon(win, ico)
                    win.destroy()
                    root.update()

            cycle(5)  # warm up Tk's font/theme caches
            gdi0, user0 = self._resources()
            cycle(50)
            gdi1, user1 = self._resources()
            self.assertLessEqual(gdi1 - gdi0, 50)
            self.assertLessEqual(user1 - user0, 50)
        finally:
            root.destroy()
            uf_toolbox._WIN_ICONS.clear()


if __name__ == '__main__':
    unittest.main()
