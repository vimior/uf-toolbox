# -*- coding: utf-8 -*-
"""Auto-hiding scrollbar."""
import tkinter as tk


class AutoHideScrollbar(tk.Scrollbar):
    """Scrollbar that auto-hides while its content is fully visible.

    Pack parameters are remembered from the first pack() call and reused
    when the scrollbar is shown again (pack layout only).
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._pack_opts = {}
        self._target = None
        self._before = None
        self._last_frac = None
        self._poll_job = None
        self._on_visibility = None

    def pack(self, **kwargs):
        self._pack_opts = kwargs
        super().pack(**kwargs)

    def attach(self, target, interval_ms=200, on_visibility=None, before=None):
        """跟踪目标组件：内容/滚动变化自动更新显隐。

        yscrollcommand 只在滚动/布局变化时触发 — 内容直接 insert/delete
        不会触发，这里用轻量轮询兜底（间隔 *interval_ms*，分数变化才更新）。

        *on_visibility*: 滚动条显隐切换时回调 ``on_visibility(visible)``
        （调用方可用于调整占位留白等）。

        *before*: 重新 pack 时的插入参考（必须与滚动条同父的兄弟组件）。
        默认用 *target*（适用于滚动条与 target 同父的场景）。
        """
        self._target = target
        self._before = before
        self._last_frac = None
        self._on_visibility = on_visibility
        self.bind('<Destroy>', self._on_destroy)
        self._poll_job = self.after(interval_ms, self._poll)

    def _on_destroy(self, _e=None):
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:
                pass
            self._poll_job = None

    def _poll(self):
        self._poll_job = None
        if not self.winfo_exists() or self._target is None:
            return
        try:
            self._target.update_idletasks()
            if self.cget('orient') == tk.HORIZONTAL:
                frac = self._target.xview()
            else:
                frac = self._target.yview()
            if frac != self._last_frac:
                self._last_frac = frac
                self.set(*frac)
        except tk.TclError:
            return
        if self.winfo_exists():
            self._poll_job = self.after(200, self._poll)

    def set(self, first, last):
        # 当内容完全可见时（first为0，last为1），隐藏滚动条
        visible = float(first) <= 0.0 and float(last) >= 1.0
        if visible:
            # 只在当前已 pack 时才 forget — 避免 pack 布局变化
            # 再次触发 yscrollcommand 造成振荡
            if self.winfo_manager():
                self.pack_forget()
                self._notify_visibility(False)
        elif not self.winfo_manager():
            # 否则，显示滚动条（复用首次 pack 的位置参数）。
            # before=...：重新 pack 会排到队列末尾、被占满的
            # 目标组件挤掉 — 插回参考组件之前恢复原始布局顺序。
            if self._target is not None:
                before = self._before if self._before is not None else self._target
                try:
                    super().pack(before=before, **self._pack_opts)
                except tk.TclError:
                    super().pack(**self._pack_opts)
            elif self._pack_opts:
                super().pack(**self._pack_opts)
            elif self.cget('orient') == tk.HORIZONTAL:
                super().pack(side='bottom', fill='x')
            else:
                super().pack(side='right', fill='y')
            self._notify_visibility(True)

        # 必须调用父类的 set 方法，保证滚动条本身的功能正常
        super().set(first, last)

    def _notify_visibility(self, visible):
        if self._on_visibility is not None:
            try:
                self._on_visibility(visible)
            except Exception:
                pass
