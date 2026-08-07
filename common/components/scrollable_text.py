# -*- coding: utf-8 -*-
"""Text widget with a built-in auto-hiding themed scrollbar."""
import tkinter as tk


class ScrollableText(tk.Text):
    """Text with built-in auto-hiding themed scrollbars (vertical ± horizontal).

    insert/delete are overridden so content changes refresh scrollbar
    visibility directly — no polling, no caller cooperation.
    """

    def __init__(self, master, sb_y=None, sb_x=None, **kwargs):
        self._sb_y = sb_y
        self._sb_x = sb_x
        self._sb_updating = False
        super().__init__(master, **kwargs)
        self.bind('<Configure>', self._on_configure, add='+')

    def pack(self, **kwargs):
        # 先 pack 自身，再把滚动条插到 Text 之前（before 要求参考已 pack）
        super().pack(**kwargs)
        if self._sb_y is not None:
            self._sb_y.pack(side=tk.RIGHT, fill=tk.Y, before=self)
        if self._sb_x is not None:
            self._sb_x.pack(side=tk.BOTTOM, fill=tk.X, before=self)

    def insert(self, *args, **kwargs):
        super().insert(*args, **kwargs)
        self._refresh_sb()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self._refresh_sb()

    def _on_configure(self, _e=None):
        self._refresh_sb()

    def _refresh_sb(self):
        # after(0) 是 timer 任务 — update_idletasks 不会执行它，
        # 避免 _apply_sb 内 update_idletasks → Configure → 再注册 → 无限递归
        self.after(0, self._apply_sb)

    def _apply_sb(self):
        if self._sb_updating:
            return
        self._sb_updating = True
        try:
            self.update_idletasks()
            if self._sb_y is not None:
                self._sb_y.set(*self.yview())
            if self._sb_x is not None:
                self._sb_x.set(*self.xview())
        except tk.TclError:
            pass
        finally:
            self._sb_updating = False
