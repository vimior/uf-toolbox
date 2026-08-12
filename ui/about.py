# -*- coding: utf-8 -*-
"""UI component — about."""
import tkinter as tk
from common.state import AppState
from common.common import FONT_FAMILY, __version__


class AboutUI(AppState, tk.Tk):

    def init(self):
        super().init()
        self._about_win = None
        self.on('window:open-about', self._show_about)
        self.on('theme:changed', lambda name: AboutUI.apply_theme(self, name))
        self.on('lang:changed', lambda name: AboutUI.apply_lang(self, name))

    def _show_about(self):
        """Show the About dialog."""
        if hasattr(self, '_about_win') and self._about_win and self._about_win.winfo_exists():
            self._about_win.lift()
            self._about_win.focus_force()
            return
        l = self.lang
        win = self.components.Toplevel(self)
        win.title(l['menu_about'])
        win.resizable(False, False)
        win.transient(self)
        frm = self.components.Frame(win)
        frm.pack(padx=8, pady=(8, 4))
        self.components.Label(
            frm, text=l['about_text'].format(__version__),
            justify=tk.CENTER, font=self.components.font(10)).pack()
        win.update_idletasks()
        self.emit('window:set-geometry', win, w=260, h=150)
        self._about_win = win
        win.bind('<Destroy>', lambda _: setattr(self, '_about_win', None))

    def apply_theme(self, name):
        """Recreate the About dialog if it exists, to apply theme changes."""
        self._recreate_about()

    def apply_lang(self, name):
        """Recreate the About dialog if it exists, to apply language changes."""
        self._recreate_about()

    def _recreate_about(self):
        """Rebuild About dialog in-place — new replaces old seamlessly."""
        if not hasattr(self, '_about_win') or self._about_win is None or not self._about_win.winfo_exists():
            return
        old_win = self._about_win
        geo = old_win.geometry()
        self._about_win = None
        self._show_about()
        self._about_win.geometry(geo)
        old_win.unbind('<Destroy>')
        old_win.destroy()
