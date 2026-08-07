# -*- coding: utf-8 -*-
"""Theme-aware UI components — exposed as app.components / self.components.

Method names & arguments mirror the corresponding tkinter classes; themed
defaults are applied only when the caller doesn't override them.
"""
import tkinter as tk

from .scrollbar import AutoHideScrollbar
from .scrollable_text import ScrollableText
from .scrollable_canvas import ScrollableCanvas


class Components:
    def __init__(self, app):
        self._app = app

    def __getattr__(self, name):
        """Fallback: forward any undefined name to the tkinter module.

        e.g. self.components.Button(...) works even though Components only
        defines themed wrappers for some widgets.
        """
        return getattr(tk, name)

    def Scrollbar(self, master, **kwargs):
        """Same as tk.Scrollbar — with themed default colors."""
        t = self._app.theme
        kwargs.setdefault('orient', tk.VERTICAL)
        kwargs.setdefault('width', 12)
        kwargs.setdefault('relief', tk.FLAT)
        kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('bg', t['scroll_bar'])
        kwargs.setdefault('troughcolor', t['scroll_frame'])
        return AutoHideScrollbar(master, **kwargs)

    def ScrollableText(self, master, scrollbars='y', **kwargs):
        """Text with built-in auto-hiding themed scrollbars.

        Content changes (insert/delete) and layout changes auto-update the
        scrollbar visibility — no attach/polling needed. Pack the returned
        Text as usual; the scrollbars are laid out automatically.

        *scrollbars*: 'y' (vertical only, default), 'x', or 'both'.

        Themed default colors are applied unless the caller overrides them.
        """
        t = self._app.theme
        kwargs.setdefault('bg', t['text_bg'])
        kwargs.setdefault('fg', t['fg'])
        kwargs.setdefault('insertbackground', t['fg'])
        kwargs.setdefault('relief', tk.FLAT)
        kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('padx', 6)
        kwargs.setdefault('pady', 6)
        kwargs.setdefault('font', ('Consolas', 9))
        sb_y = self.Scrollbar(master) if scrollbars in ('y', 'both') else None
        sb_x = (self.Scrollbar(master, orient=tk.HORIZONTAL)
                if scrollbars in ('x', 'both') else None)
        txt = ScrollableText(master, sb_y, sb_x, **kwargs)
        if sb_y is not None:
            txt.configure(yscrollcommand=sb_y.set)
            sb_y.config(command=txt.yview)
        if sb_x is not None:
            txt.configure(xscrollcommand=sb_x.set)
            sb_x.config(command=txt.xview)
        return txt

    def ScrollableCanvas(self, master, scrollbars='y', **kwargs):
        """Canvas with built-in auto-hiding themed scrollbars.

        Content lives in the returned canvas's ``inner`` Frame; its
        <Configure> drives scrollregion + scrollbar visibility — no
        attach/polling needed. Pack the returned Canvas as usual.

        *scrollbars*: 'y' (vertical only, default), 'x', or 'both'.

        Themed default colors are applied unless the caller overrides them.
        """
        t = self._app.theme
        kwargs.setdefault('bg', t['bg'])
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('borderwidth', 0)
        sb_y = self.Scrollbar(master) if scrollbars in ('y', 'both') else None
        sb_x = (self.Scrollbar(master, orient=tk.HORIZONTAL)
                if scrollbars in ('x', 'both') else None)
        cv = ScrollableCanvas(master, sb_y, sb_x, **kwargs)
        if sb_y is not None:
            cv.configure(yscrollcommand=sb_y.set)
            sb_y.config(command=cv.yview)
        if sb_x is not None:
            cv.configure(xscrollcommand=sb_x.set)
            sb_x.config(command=cv.xview)
        return cv
