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
        self._master = master
        self._master_padx = None  # master 的 pack 右 padx（滚动条边距），首次显示时记录
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
        self._interval_ms = interval_ms
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
            self._poll_job = self.after(self._interval_ms, self._poll)

    def set(self, first, last):
        # 当内容完全可见时（first为0，last为1），隐藏滚动条，
        # 并释放 master 的右 padx — 内容扩展到滚动条原位置（宽度不浪费）。
        visible = float(first) <= 0.0 and float(last) >= 1.0
        if visible:
            if self.winfo_manager():
                self.pack_forget()
                self._notify_visibility(False)
                self._apply_master_padx(False)
        elif not self.winfo_manager():
            # 否则，显示滚动条（复用首次 pack 的位置参数），
            # 并恢复 master 的右 padx（滚动条边距）。
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
            self._apply_master_padx(True)

        # 必须调用父类的 set 方法，保证滚动条本身的功能正常
        super().set(first, last)

    def _apply_master_padx(self, visible):
        """滚动条显示/隐藏时调整 master 的 pack 右 padx。

        隐藏 → 右 padx 归零（内容扩展到滚动条位置）；
        显示 → 恢复原右 padx（滚动条与窗口边缘的边距）。
        """
        if self._master is None:
            return
        try:
            # 仅 pack 布局下调整 master 的 padx:
            # Toplevel/Tk 由 wm 管理 (winfo_manager 返回 'wm'), grid 布局返回
            # 'grid' — 均无 pack padx 语义, 跳过 (Toplevel 也无 pack_info 方法)
            if self._master.winfo_manager() != 'pack':
                return
            if self._master_padx is None:
                info = self._master.pack_info()
                p = info.get('padx', 0)
                if isinstance(p, tuple) and len(p) == 2:
                    self._master_padx = p
                elif isinstance(p, str) and ' ' in p:
                    self._master_padx = tuple(int(x) for x in p.split())
                else:
                    self._master_padx = int(p or 0)
            if visible:
                self._master.pack_configure(padx=self._master_padx)
            else:
                left = (self._master_padx[0]
                        if isinstance(self._master_padx, tuple)
                        else self._master_padx)
                self._master.pack_configure(padx=(left, 0))
        except (tk.TclError, ValueError):
            pass

    def _notify_visibility(self, visible):
        if self._on_visibility is not None:
            try:
                self._on_visibility(visible)
            except Exception:
                pass
