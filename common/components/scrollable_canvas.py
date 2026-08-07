# -*- coding: utf-8 -*-
"""Canvas with a built-in auto-hiding themed scrollbar + inner frame."""
import tkinter as tk


class ScrollableCanvas(tk.Canvas):
    """Canvas with built-in auto-hiding themed scrollbars (vertical ± horizontal).

    Content lives in ``self.inner`` (a Frame placed inside the canvas);
    its <Configure> drives scrollregion + scrollbar visibility — no
    polling, no caller cooperation.
    """

    def __init__(self, master, sb_y=None, sb_x=None, **kwargs):
        self._sb_y = sb_y
        self._sb_x = sb_x
        self._sb_updating = False
        bg = kwargs.get('bg')
        super().__init__(master, **kwargs)
        self.inner = tk.Frame(self, bg=bg)
        self._win_id = self.create_window(
            (0, 0), window=self.inner, anchor=tk.NW)
        self._inner_w = 0
        self.inner.bind('<Configure>', self._on_inner_configure, add='+')
        self.bind('<Configure>', self._on_configure, add='+')
        # 内置鼠标滚轮（Enter 时全局绑定，Leave 时解除 — 覆盖子 widget）
        self.bind('<Enter>', self._on_mw_enter, add='+')
        self.bind('<Leave>', self._on_mw_leave, add='+')
        self.inner.bind('<Enter>', self._on_mw_enter, add='+')
        self.inner.bind('<Leave>', self._on_mw_leave, add='+')

    def _on_mousewheel(self, event):
        self.yview_scroll(int(-event.delta / 120), 'units')

    def _on_mw_enter(self, _e=None):
        self.bind_all('<MouseWheel>', self._on_mousewheel)

    def _on_mw_leave(self, _e=None):
        self.unbind_all('<MouseWheel>')

    def pack(self, **kwargs):
        # 先 pack 自身，再把滚动条插到 Canvas 之前（before 要求参考已 pack）
        super().pack(**kwargs)
        if self._sb_y is not None:
            self._sb_y.pack(side=tk.RIGHT, fill=tk.Y, before=self)
        if self._sb_x is not None:
            self._sb_x.pack(side=tk.BOTTOM, fill=tk.X, before=self)

    def _on_inner_configure(self, _e=None):
        self.configure(scrollregion=self.bbox('all'))
        self._refresh_sb()

    def _on_configure(self, _e=None):
        # 无横向滚动条时 inner 铺满可视区；有横向滚动条时保持内容宽度（可横滚）
        if self._sb_x is None:
            w = self.winfo_width()
            if w != self._inner_w:
                self._inner_w = w
                self.itemconfig(self._win_id, width=w)
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
