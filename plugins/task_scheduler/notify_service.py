# -*- coding: utf-8 -*-
"""Notification service — ServicePlugin, provides popup notifications.

Services for other plugins / task callbacks (all accept ``unique=False``;
``unique=True`` 每次新建独立窗口 — 不复用、不覆盖, toast/banner 从角落
依次堆叠, popup 转为非模态, canvas 独立居中可用 x/y 定位;
toast 的 ``x``/``y`` 同时指定 = 绝对定位, 退出堆叠系统, 位置完全由
调用方控制):
  notify@toast (text=None, *, timeout=3, duration=300, position='br',
                bg='#333333', fg='#ffffff', font_size=10,
                width=0, height=0, x=None, y=None, show_time=True)
  notify@popup (text=None, *, title=None, timeout=0, width=360, height=200,
                bg='#2b2b2b', fg='#e0e0e0', font_size=10,
                x=None, y=None, show_time=True)
  notify@banner(text=None, *, timeout=5, duration=400,
                bg='#2d5a8a', fg='#ffffff', font_size=11,
                width=0, height=0, show_time=True)
  notify@canvas(text=None, *, pattern='flower', title=None, timeout=0,
                width=300, height=360, bg='#1a1a2e', fg='#f0e68c',
                font_size=13, x=None, y=None, show_time=True)
"""
import queue
import sys
import math
import time
import tkinter as tk
from typing import Literal

if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

from plugins.plugin import ServicePlugin

# ---------------------------------------------------------------------------
# flower petal colours (shared)
# ---------------------------------------------------------------------------
_PETAL_COLORS = ('#ff6b8a', '#ff8fab', '#ffb3c6', '#ff6b8a',
                 '#ff8fab', '#ffb3c6', '#ff6b8a', '#ff8fab')

#: 堆叠窗口间间距 (px)
_STACK_GAP = 2

#: unique 堆叠限制: 最大窗口数 / 最大总高度 (屏幕高度比例)
_MAX_STACK = 10
_MAX_STACK_RATIO = 0.6


def _work_area(root):
    """工作区 (排除任务栏), 返回 (left, top, right, bottom).

    Windows 用 SPI_GETWORKAREA (任务栏任意位置/高度都正确);
    其它平台回退屏幕尺寸.
    """
    if sys.platform == 'win32':
        try:
            rect = wintypes.RECT()
            ctypes.windll.user32.SystemParametersInfoW(
                0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
            return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
    return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight())


if sys.platform == 'win32':
    FONT_FAMILY = 'Microsoft YaHei'
elif sys.platform == 'darwin':
    FONT_FAMILY = 'PingFang SC'
else:
    FONT_FAMILY = 'Ubuntu'

# ===================================================================
# popup base
# ===================================================================

class _NotifyBase(tk.Toplevel):
    """Shared base: auto-close timer, refresh support, cleanup."""

    # 样式类级默认 (子类覆盖): refresh 未传入的参数回退到类默认,
    # 不继承上次调用的自定义样式
    _DEF_BG = '#2b2b2b'
    _DEF_FG = '#ffffff'
    _DEF_FONT_SIZE = 10
    _DEF_TIME_FONT_SIZE = 9
    _DEF_TIME_FG = None
    _DEF_SHOW_TIME = True

    @staticmethod
    def _i(v, default=0):
        """Convert *v* to int. Accepts int/float or pure-digit str; raises on garbage."""
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        raise ValueError(f'expected int, got {v!r}')

    @staticmethod
    def _parse_show_time(v):
        """Parse show_time value to boolean."""
        return v not in (False, 0, '0', 'False', 'false', '')

    def __init__(self, owner, timeout=0, show_time=True,
                 bg=None, fg=None, font_size=None,
                 time_font_size=None, time_fg=None):
        super().__init__(owner.root)
        self.geometry('+30000+30000')  # park far off-screen during build
        self.update_idletasks()  # force the geometry to take effect
        self.withdraw()
        self._owner = owner
        self._components = getattr(owner, 'components', tk)
        self._timeout = self._i(timeout)
        self._timer_id = None
        cls = type(self)
        self._show_time = self._parse_show_time(show_time)
        self._bg = cls._DEF_BG if bg is None else bg
        self._fg = cls._DEF_FG if fg is None else fg
        self._font_size = (cls._DEF_FONT_SIZE if font_size is None
                           else font_size)
        self._time_font_size = (cls._DEF_TIME_FONT_SIZE
                                if time_font_size is None
                                else time_font_size)
        self._time_fg = cls._DEF_TIME_FG if time_fg is None else time_fg
        self.configure(bg=self._bg)
        self.transient(owner.root)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self._reset_timer()
        self.bind('<Button-1>', lambda e: self._on_click())

    # -- timer --
    def _reset_timer(self):
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        if self._timeout > 0:
            self._timer_id = self.after(self._timeout * 1000, self.destroy)

    def _on_click(self):
        """点击: 默认延迟 3 秒后关闭 (popup 覆盖为立即关闭)"""
        self._timeout = 3
        self._reset_timer()

    def destroy(self):
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        owner = getattr(self, '_owner', None)
        super().destroy()
        if owner is not None:
            owner._popup_closed(self)  # 通知 owner 清理引用 (防 pathname 复用误判)

    def refresh(self, text='', timeout=None, **kw):
        """Override in subclasses to update content and reset timer.

        复用窗口每次调用按参数完整渲染: 未传入的样式参数回退到类默认,
        不继承上次调用的自定义样式.
        """
        cls = type(self)
        self._bg = kw.get('bg', cls._DEF_BG)
        self._fg = kw.get('fg', cls._DEF_FG)
        self._font_size = kw.get('font_size', cls._DEF_FONT_SIZE)
        self._time_font_size = kw.get('time_font_size',
                                      cls._DEF_TIME_FONT_SIZE)
        self._time_fg = kw.get('time_fg', cls._DEF_TIME_FG)
        self._show_time = self._parse_show_time(
            kw.get('show_time', cls._DEF_SHOW_TIME))
        if text is not None:
            self._apply_text(text)
        self._apply_style()
        self._refresh_time_label()
        if 'width' in kw or 'height' in kw:
            w = self._i(kw.get('width', 0), 0) or self.winfo_width()
            h = self._i(kw.get('height', 0), 0) or self.winfo_height()
            self._apply_geometry(w, h)
        # x/y 任一提供即尝试定位 (须两者齐全才生效); 与 Canvas 原 OR 逻辑统一
        if 'x' in kw or 'y' in kw:
            px = self._i(kw.pop('x', None), None)
            py = self._i(kw.pop('y', None), None)
            if px is not None and py is not None:
                self._apply_position(px, py)
        if timeout is not None:
            self._timeout = self._i(timeout)
        self._reset_timer()
        self.lift()
        self.focus_force()

    def _apply_style(self):
        """Apply bg/fg/font_size to all common widgets."""
        self.configure(bg=self._bg)
        if hasattr(self, '_frame'):
            self._frame.configure(bg=self._bg)
        if hasattr(self, '_label'):
            self._label.configure(bg=self._bg, fg=self._fg,
                                  font=(FONT_FAMILY, self._font_size))
        if hasattr(self, '_time_label'):
            self._time_label.configure(bg=self._bg,
                                        fg=self._time_fg or self._fg,
                                        font=self._components.mono_font(self._time_font_size))

    def _apply_text(self, text):
        if hasattr(self, '_label'):
            self._label.configure(text=text)

    def _notify_reflow(self):
        """高度/位置变化影响后续堆叠 → 通知 owner 重排 (防御: owner 无此方法时跳过)"""
        reflow = getattr(self._owner, '_reflow', None)
        if reflow is not None:
            reflow(getattr(self, '_notify_style', None))

    def _refresh_time_label(self):
        if hasattr(self, '_time_label'):
            if self._show_time:
                self._time_label.configure(text=time.strftime('%Y-%m-%d %H:%M:%S'))
                self._time_label.pack(fill=tk.X)
            else:
                self._time_label.pack_forget()

    def _apply_geometry(self, w, h):
        """Override in subclasses for custom geometry handling."""
        self.geometry(f'{w}x{h}')

    def _apply_position(self, x, y):
        """Override in subclasses for custom position handling."""
        self.geometry(f'+{x}+{y}')


# ===================================================================
# Toast — corner slide-in notification
# ===================================================================

class _Toast(_NotifyBase):
    """Small notification that slides in from a screen corner."""

    _DEF_BG = '#333333'
    _DEF_FG = '#ffffff'
    _DEF_FONT_SIZE = 10
    _DEF_TIME_FONT_SIZE = 8

    _POS = {
        'br': (1.0, 1.0, 's', -1),   # bottom-right → slide up
        'bl': (0.0, 1.0, 's', -1),   # bottom-left  → slide up
        'tr': (1.0, 0.0, 'n', -1),   # top-right    → slide down
        'tl': (0.0, 0.0, 'n', -1),   # top-left     → slide down
    }

    def __init__(self, owner, text=None, timeout=3, duration=300,
                 position='br', bg=None, fg=None,
                 font_size=None, width=0, height=0,
                 x=None, y=None, stack_offset=0, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=_kw.pop('time_font_size', None),
                         time_fg=_kw.pop('time_fg', None))
        self.overrideredirect(True)
        self.attributes('-topmost', True)

        self._duration = self._i(duration, 300)
        self._position = position  # 堆叠按角标分组 (不同 position 各自成链)

        if text is None:
            text = ''
        _w = self._i(width)
        _h = self._i(height)
        _x = x if x is None else self._i(x, None)
        _y = y if y is None else self._i(y, None)

        # build content
        wraplen = max(200, _w - 40) if _w else 340
        self._frame = self._components.Frame(self, bg=self._bg, padx=16, pady=10)
        self._frame.pack(fill=tk.BOTH, expand=True)

        self._label = self._components.Label(self._frame, text=text, font=(FONT_FAMILY, self._font_size),
                               bg=self._bg, fg=self._fg, wraplength=wraplen,
                               anchor='center', justify=tk.CENTER)
        self._label.pack(fill=tk.BOTH, expand=True)

        self._time_label = self._components.Label(self._frame, text='',
                                     font=self._components.mono_font(self._time_font_size),
                                     bg=self._bg, fg=self._fg)
        self._refresh_time_label()

        self.update_idletasks()

        sh = self.winfo_screenheight()
        w = _w if _w > 0 else self.winfo_reqwidth()
        h = _h if _h > 0 else self.winfo_reqheight()

        # calculate target position
        if x is not None and y is not None:
            tx, ty = _x, _y
            start_dir = 's' if ty > sh / 2 else 'n'
            self._free_placed = True  # 绝对定位: 退出堆叠系统
        else:
            tx, ty, start_dir = self._calc_pos(position, w, h)
            self._free_placed = False

        self._base_y = ty  # 基准位 (offset 前): 重排时归位用
        # 独立窗口堆叠: 按前序窗口累计高度偏移 (底部角落上移, 顶部角落下移);
        # 绝对定位窗口不叠加偏移
        if stack_offset and not self._free_placed:
            if ty > sh / 2:
                ty -= stack_offset
            else:
                ty += stack_offset

        if start_dir == 's':
            start_y = sh
        else:
            start_y = -h

        # 动画目标存实例: 重排 (_place_at) 时更新目标, 进行中的动画滑向新位置
        self._anim_target = (tx, ty)
        self._target_y = ty  # 稳态目标 y: reflow 读取 (动画中 winfo_y 不可靠)
        self.geometry(f'{w}x{h}+{tx}+{start_y}')
        self.deiconify()
        self._animate_in(0)

    def _animate_in(self, step):
        step += 1
        total = max(1, int(self._duration / 10))
        progress = min(1.0, step / total)
        # ease-out: 1 - (1-t)^2
        eased = 1 - (1 - progress) ** 2
        tx, ty = self._anim_target
        cy = int(ty + (1 - eased) * (self.winfo_y() - ty))
        self.geometry(f'+{tx}+{cy}')
        if step < total:
            self.after(10, lambda: self._animate_in(step))

    def _place_at(self, y):
        """重排: 移动到指定 y (动画目标同步, 进行中的动画滑向新位置)"""
        if y == self._target_y:
            return
        tx = self.winfo_x()
        self._target_y = y
        self._anim_target = (tx, y)
        self.geometry(f'+{tx}+{y}')

    def _calc_pos(self, position, w, h):
        """计算角标目标位置 + 滑入方向 (底角上滑/顶角下滑).

        *position*: 角标键名 ('br'/'bl'/'tr'/'tl'), *w*/*h*: 窗口宽高.
        基于工作区 (排除任务栏, 任务栏任意位置/高度都不覆盖), 四边 12px 边距.
        """
        rx, ry, _, start_dir = self._POS.get(position, self._POS['br'])
        wl, wt, wr, wb = _work_area(self.winfo_toplevel())
        tm = 12
        tx = int((wr - wl - w) * rx) + wl - (tm if rx > 0.5 else -tm)
        # 底部角落向下留 12, 顶部角落向下 12 (窗口不超出工作区)
        ty = int((wb - wt - h) * ry) + wt - (tm if ry > 0.5 else -tm)
        return tx, ty, start_dir

    def refresh(self, text='', timeout=None, **kw):
        if 'position' in kw:
            tx, ty, _ = self._calc_pos(kw['position'],
                                       self.winfo_width(), self.winfo_height())
            self.geometry(f'+{tx}+{ty}')
            self._target_y = ty
        super().refresh(text, timeout, **kw)
        if 'height' not in kw:
            # 内容变化后按请求高度重算 (复用刷新: 文字变长/变短高度跟随)
            self.update_idletasks()
            h = self.winfo_reqheight()
            if h != self.winfo_height():
                y = self.winfo_y()
                if y > self.winfo_screenheight() / 2:
                    # 底部角落: 保持底部对齐, 高度变化时顶部移动
                    y += self.winfo_height() - h
                self.geometry(f'{self.winfo_width()}x{h}'
                              f'+{self.winfo_x()}+{y}')
                self._target_y = y  # 同步稳态目标, reflow 幂等判断才准确
                # 高度变化影响后续堆叠 → 通知 owner 重排
                self._notify_reflow()

    def destroy(self):
        self.attributes('-topmost', False)
        super().destroy()


# ===================================================================
# Popup — centred dialog
# ===================================================================

class _Popup(_NotifyBase):
    """Centred dialog — click anywhere to dismiss."""

    _DEF_BG = '#2b2b2b'
    _DEF_FG = '#e0e0e0'

    def __init__(self, owner, text=None, title=None, timeout=0,
                 width=360, height=200, bg=None, fg=None,
                 font_size=None, x=None, y=None, grab=True, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=_kw.pop('time_font_size', None),
                         time_fg=_kw.pop('time_fg', None))
        self.resizable(False, False)
        self._grab = grab

        if text is None:
            text = ''
        if title:
            self.title(title)
        _w = self._i(width, 360) or 360
        _h = self._i(height, 200) or 200

        self._frame = self._components.Frame(self, bg=self._bg)
        self._frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        self._label = self._components.Label(self._frame, text=text, font=(FONT_FAMILY, self._font_size),
                               bg=self._bg, fg=self._fg, wraplength=_w - 40,
                               anchor='center', justify=tk.CENTER)
        self._label.pack(fill=tk.BOTH, expand=True)

        self._time_label = self._components.Label(self._frame, text='',
                                     font=self._components.mono_font(self._time_font_size),
                                     bg=self._bg, fg=self._fg)
        self._refresh_time_label()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = self._i(x, None) if x is not None else (sw - _w) // 2
        py = self._i(y, None) if y is not None else (sh - _h) // 2
        self.geometry(f'{_w}x{_h}+{px}+{py}')
        self.deiconify()
        if self._grab:
            self.grab_set()
        self.focus_set()

    def _on_click(self):
        """点击任意处关闭"""
        self.destroy()

    def refresh(self, text='', timeout=None, **kw):
        if 'title' in kw:
            self.title(kw['title'])
        super().refresh(text, timeout, **kw)


# ===================================================================
# Banner — top-of-screen slide-down strip
# ===================================================================

class _Banner(_NotifyBase):
    """Full-width banner that slides down from the top of the screen."""

    _DEF_BG = '#2d5a8a'
    _DEF_FG = '#ffffff'
    _DEF_FONT_SIZE = 11

    def __init__(self, owner, text=None, timeout=5, duration=400,
                 bg=None, fg=None, font_size=None,
                 width=0, height=0, stack_offset=0, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=_kw.pop('time_font_size', None),
                         time_fg=_kw.pop('time_fg', None))
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self._duration = self._i(duration, 400)

        if text is None:
            text = ''

        wl, _wt, wr, _wb = _work_area(self.winfo_toplevel())
        wa_w = wr - wl
        _bw = self._i(width)
        bw = _bw if _bw > 0 else wa_w

        self._frame = self._components.Frame(self, bg=self._bg, padx=20, pady=8)
        self._frame.pack(fill=tk.BOTH, expand=True)
        # wraplength 换行: 内容多行时请求高度随行数增长, 高度重算才有效
        self._label = self._components.Label(self._frame, text=text,
                               font=(FONT_FAMILY, self._font_size),
                               bg=self._bg, fg=self._fg,
                               anchor='center', justify=tk.CENTER,
                               wraplength=max(200, bw - 40))
        self._label.pack(fill=tk.BOTH, expand=True)

        self._time_label = self._components.Label(self._frame, text='',
                                     font=self._components.mono_font(self._time_font_size),
                                     bg=self._bg, fg=self._fg)
        self._refresh_time_label()

        self.update_idletasks()
        _bh = self._i(height)
        h = _bh if _bh > 0 else self.winfo_reqheight()
        self._anim_h = h  # 动画路径用实际高度 (显式 height 时与 reqheight 可能不同)
        self._base_y = 0  # 基准位 (顶部): 重排时归位用
        # 独立窗口堆叠: 按前序窗口累计高度从顶部向下错开
        self._target_y = stack_offset
        bx = wl + (wa_w - bw) // 2
        self.geometry(f'{bw}x{h}+{bx}+{-h - self._target_y}')
        self.deiconify()
        self._animate_in(bx, 0)

    def _animate_in(self, bx, step):
        step += 1
        total = max(1, int(self._duration / 10))
        progress = min(1.0, step / total)
        eased = 1 - (1 - progress) ** 2
        y = int(self._target_y - self._anim_h * (1 - eased))
        self.geometry(f'+{bx}+{y}')
        if step < total:
            self.after(10, lambda bx=bx, s=step: self._animate_in(bx, s))

    def _place_at(self, y):
        """重排: 移动到指定 y (动画目标同步, 进行中的动画滑向新位置)"""
        if y == self._target_y:
            return
        self._target_y = y
        self.geometry(f'+{self.winfo_x()}+{y}')

    def refresh(self, text='', timeout=None, **kw):
        # 宽度变化时同步换行宽度 (内容多行 → 高度重算有效)
        w = self._i(kw.get('width', 0), 0) or self.winfo_width()
        self._label.configure(wraplength=max(200, w - 40))
        super().refresh(text, timeout, **kw)
        if 'height' not in kw:
            # 内容变化后按请求高度重算窗口高度 (复用窗口刷新: 文字变长/
            # 变短时高度跟随, 位置不变)
            self.update_idletasks()
            h = self.winfo_reqheight()
            if h != self._anim_h:
                self._anim_h = h
                self.geometry(f'{self.winfo_width()}x{h}')
                # 高度变化影响后续堆叠 → 通知 owner 重排
                self._notify_reflow()

    def destroy(self):
        self.attributes('-topmost', False)
        super().destroy()


# ===================================================================
# Canvas — decorative popup with multiple drawing patterns
# ===================================================================

class _Canvas(_NotifyBase):
    """Decorative canvas popup with multiple drawing patterns."""

    _DEF_BG = '#1a1a2e'
    _DEF_FG = '#f0e68c'
    _DEF_FONT_SIZE = 13
    _DEF_TIME_FG = '#888888'

    _PATTERNS = ('flower', 'heart', 'star', 'sun', 'smiley')

    _TITLES = {'flower': '🌸', 'heart': '❤️', 'star': '⭐', 'sun': '☀️', 'smiley': '😊'}
    _SIZES = {'flower': (300, 360), 'heart': (280, 300),
              'star': (280, 300), 'sun': (300, 310), 'smiley': (280, 300)}

    def __init__(self, owner, text=None, timeout=0, title=None, pattern='flower',
                 width=None, height=None, bg=None, fg=None,
                 font_size=None, x=None, y=None, time_font_size=None,
                 time_fg=None, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=time_font_size, time_fg=time_fg)
        self.resizable(False, False)

        self._text = text if text is not None else ''
        self._pattern = pattern if pattern in self._PATTERNS else 'flower'
        if title is None:
            title = self._TITLES.get(self._pattern, '🌸')
        self.title(title)
        dw, dh = self._SIZES.get(self._pattern, (300, 360))
        self._fw = dw if width is None else (self._i(width, dw) or dw)
        self._fh = dh if height is None else (self._i(height, dh) or dh)

        self._canvas = self._components.Canvas(self, width=self._fw, height=self._fh,
                                 bg=self._bg, highlightthickness=0)
        self._canvas.pack()
        self._draw()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        px = self._i(x, None) if x is not None else (sw - self._fw) // 2
        py = self._i(y, None) if y is not None else (sh - self._fh) // 2
        self.geometry(f'{self._fw}x{self._fh}+{px}+{py}')
        self.deiconify()

    def refresh(self, text='', timeout=None, **kw):
        if text is not None:
            self._text = text
        if 'pattern' in kw:
            p = kw['pattern']
            self._pattern = p if p in self._PATTERNS else 'flower'
            if 'title' not in kw:
                self.title(self._TITLES.get(self._pattern, '🌸'))
            if 'width' not in kw and 'height' not in kw:
                dw, dh = self._SIZES.get(self._pattern, (300, 360))
                kw.setdefault('width', dw)
                kw.setdefault('height', dh)
        if 'title' in kw:
            self.title(kw['title'])
        # x/y 定位统一由基类 refresh 处理 (OR 逻辑)
        self._canvas.delete('all')
        self._draw()
        super().refresh(text, timeout, **kw)

    def _apply_geometry(self, w, h):
        if w != self._fw or h != self._fh:
            self._fw, self._fh = w, h
            self._canvas.configure(width=w, height=h)
        self.geometry(f'{w}x{h}')

    def _draw(self):
        getattr(self, f'_draw_{self._pattern}')()

    # -- text helpers --
    def _draw_text(self):
        c, w, h = self._canvas, self._fw, self._fh
        c.create_text(w / 2, h - 55,
                      text=self._text,
                      font=(FONT_FAMILY, self._font_size, 'bold'),
                      fill=self._fg)
        if self._show_time:
            c.create_text(w / 2, h - 25,
                          text=time.strftime('%Y-%m-%d %H:%M:%S'),
                          font=self._components.mono_font(self._time_font_size),
                          fill=self._time_fg or self._fg)

    # -- flower --
    def _draw_flower(self):
        c, w, h = self._canvas, self._fw, self._fh
        cx, cy = w / 2, 120
        # stem
        c.create_line(cx, cy + 30, cx, h - 110, fill='#4a7c59', width=4)
        # leaf
        lx = cx - 45
        c.create_oval(lx - 25, cy + 80, lx + 25, cy + 100,
                      fill='#5a9a6a', outline='')
        c.create_line(lx - 20, cy + 90, lx + 20, cy + 90, fill='#3d6b4a')
        # petals
        for i in range(8):
            a = math.pi * 2 / 8 * i - math.pi / 2
            px = cx + 26 * math.cos(a)
            py = cy + 26 * math.sin(a)
            r = 22
            c.create_oval(px - r, py - r, px + r, py + r,
                          fill=_PETAL_COLORS[i], outline='')
        # center
        c.create_oval(cx - 13, cy - 13, cx + 13, cy + 13,
                      fill='#ffd166', outline='#e6b800', width=2)
        self._draw_text()

    # -- heart --
    def _draw_heart(self):
        c, w, h = self._canvas, self._fw, self._fh
        cx, cy = w / 2, 115
        s = 3.0  # scale
        pts = []
        for i in range(120):
            t = math.pi * 2 * i / 119
            x = cx + s * 16 * math.sin(t) ** 3
            y = cy - s * (13 * math.cos(t) - 5 * math.cos(2 * t)
                          - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.extend([x, y])
        c.create_polygon(*pts, fill='#ff4466', outline='', smooth=True)
        self._draw_text()

    # -- star --
    def _draw_star(self):
        c, w, h = self._canvas, self._fw, self._fh
        cx, cy = w / 2, 120
        outer_r, inner_r = 55, 22
        points = []
        for i in range(10):
            a = math.pi * 2 / 10 * i - math.pi / 2
            r = outer_r if i % 2 == 0 else inner_r
            points.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        c.create_polygon(*points, fill='#ffcc00', outline='#e6b800', width=2)
        self._draw_text()

    # -- sun --
    def _draw_sun(self):
        c, w, h = self._canvas, self._fw, self._fh
        cx, cy = w / 2, 120
        # rays
        for i in range(12):
            a = math.pi * 2 / 12 * i
            inner = 35
            outer = 55 + (10 if i % 2 == 0 else 0)
            c.create_line(cx + inner * math.cos(a), cy + inner * math.sin(a),
                          cx + outer * math.cos(a), cy + outer * math.sin(a),
                          fill='#ffaa00', width=4 if i % 2 == 0 else 2)
        # body
        c.create_oval(cx - 32, cy - 32, cx + 32, cy + 32,
                      fill='#ffdd44', outline='#e6b800', width=2)
        # eyes
        c.create_oval(cx - 10, cy - 12, cx - 4, cy - 3, fill='#333')
        c.create_oval(cx + 4, cy - 12, cx + 10, cy - 3, fill='#333')
        # smile
        c.create_arc(cx - 12, cy - 5, cx + 12, cy + 15,
                     start=0, extent=-180, style=tk.ARC, outline='#333', width=2)
        self._draw_text()

    # -- smiley --
    def _draw_smiley(self):
        c, w, h = self._canvas, self._fw, self._fh
        cx, cy = w / 2, 120
        r = 55
        c.create_oval(cx - r, cy - r, cx + r, cy + r,
                      fill='#ffdd44', outline='#e6b800', width=3)
        # eyes
        c.create_oval(cx - 18, cy - 18, cx - 8, cy - 5, fill='#333')
        c.create_oval(cx + 8, cy - 18, cx + 18, cy - 5, fill='#333')
        # smile
        c.create_arc(cx - 25, cy - 10, cx + 25, cy + 30,
                     start=0, extent=-180, style=tk.ARC, outline='#333', width=3)
        self._draw_text()

    def destroy(self):
        self._canvas = None
        super().destroy()


# ===================================================================
# NotifyService
# ===================================================================

class NotifyService(ServicePlugin):
    """Headless service that provides four popup notification styles."""

    name = 'Notifications'
    name_zh = '通知服务'
    namespace = 'notify'

    _WAKEUP_EVENT = '<<NotifyPoll>>'

    def __init__(self, app=None):
        super().__init__(app)
        self._popups = {}  # style -> _NotifyBase instance (复用窗口)
        self._unique_windows = []  # unique=True 的独立窗口列表
        self._queue = queue.Queue()  # (style, text, kw) 请求队列

        s = self.services
        s.register('toast', self._toast)
        s.register('popup', self._popup)
        s.register('banner', self._banner)
        s.register('canvas', self._canvas)
        self._bind_wakeup()

        self.register_agent_tools()

    # -- helpers --
    _STYLES = {'toast': _Toast, 'popup': _Popup,
               'banner': _Banner, 'canvas': _Canvas}

    def _bind_wakeup(self):
        """主线程绑定唤醒事件: 非主线程发起通知时 event_generate 唤醒,
        在此统一创建/刷新窗口 (tkinter 非线程安全, 窗口操作必须主线程).

        无常驻轮询 — 生产者主动敲门, 延迟 = 事件循环一轮 (几 ms).
        """
        if self.root is not None:
            self.root.bind(self._WAKEUP_EVENT, lambda _e: self._drain_queue())

    def _drain_queue(self, _event=None):
        """主线程: 处理队列中所有待投递通知"""
        try:
            while True:
                style, text, kw = self._queue.get_nowait()
                try:
                    self._show_main(style, text, kw)
                except Exception:
                    import traceback
                    traceback.print_exc()
        except queue.Empty:
            pass

    def _show(self, style, text, **kw):
        """投递通知请求 (任意线程可调; 主线程事件循环处理)"""
        self._queue.put((style, text, kw))
        if self.root is not None:
            # 线程安全: 追加到事件队列尾部, 主线程下一轮事件循环处理
            self.root.event_generate(self._WAKEUP_EVENT, when='tail')

    def _reflow(self, style):
        """重排该 style 堆叠: 复用窗口恒基准位, unique 按创建顺序上叠.

        窗口出现/消失/高度变化后调用 — 消除空洞与重叠 (动画目标同步,
        进行中的动画平滑滑向新位置). 绝对定位 (x/y 指定) 窗口不参与.
        """
        # geometry 是异步实现的: 刚设置的新尺寸要 update 后才反映到
        # winfo_height, 否则重排基于旧高度算错位置 (窗口被跳过不移动)
        if self.root is not None:
            self.root.update_idletasks()
        # 按 position 分组: 不同角标的 toast 各自成链, 互不干扰
        # (banner 无 _position → None 组); 复用窗口按 style+position 分键,
        # 可能多个 (不同 position 各一个), 全部纳入对应组
        groups = {}
        prefix = style + ':'
        for key, p in self._popups.items():
            if (key.startswith(prefix) and p.winfo_exists()
                    and not getattr(p, '_free_placed', False)
                    and hasattr(p, '_place_at')):  # 仅堆叠类 (toast/banner)
                groups.setdefault(getattr(p, '_position', None), []).append(p)
        for w in self._unique_windows:
            if (getattr(w, '_notify_style', None) == style
                    and w.winfo_exists()
                    and not getattr(w, '_free_placed', False)
                    and hasattr(w, '_place_at')):  # popup/canvas 无堆叠语义
                groups.setdefault(getattr(w, '_position', None), []).append(w)

        sh = self.root.winfo_screenheight() if self.root is not None else 0
        for ordered in groups.values():
            if not ordered:
                continue
            # 第一个窗口 (复用或首个 unique) 归位基准; 唯一窗口也归位
            first = ordered[0]
            first._place_at(first._base_y)
            prev_y = first._target_y  # 稳态目标 (动画中 winfo_y 不可靠)
            prev_h = first.winfo_height()
            down = prev_y > sh / 2  # 底部角落向上堆 / 顶部角落向下堆
            for w in ordered[1:]:
                if down:
                    # 向上堆: 新窗口底部贴前窗口顶部 → 用自己高度
                    y = prev_y - w.winfo_height() - _STACK_GAP
                else:
                    # 向下堆: 新窗口顶部贴前窗口底部 → 用前窗口高度
                    y = prev_y + prev_h + _STACK_GAP
                w._place_at(y)
                prev_y = y
                prev_h = w.winfo_height()

    def _show_main(self, style, text, kw):
        """主线程: 创建/刷新通知窗口; 失败 re-raise 由唤醒回调捕获"""
        if kw.pop('unique', False):
            self._show_unique(style, text, kw)
            return
        # ---- 复用逻辑 (按 style+position 分键, 新通知覆盖内容) ----
        key = f'{style}:{kw.get("position")}'
        popup = self._popups.get(key)
        if popup and popup.winfo_exists():
            popup.refresh(text, **kw)
            return
        cls = self._STYLES[style]
        popup = None
        try:
            popup = cls(self, text, **kw)  # 复用窗口恒基准位 (stack_offset=0)
            popup._notify_style = style
            popup._popup_key = key
            self._popups[key] = popup
            self.app.emit('app@window:set-icon', popup)
            self._reflow(style)  # 复用占基准位, unique 被挤上去
        except Exception:
            if popup is not None:
                try:
                    popup.destroy()
                except Exception:
                    pass
            self._popups.pop(key, None)  # 清理残留引用 (防 pathname 复用误判)
            raise

    def _show_unique(self, style, text, kw):
        """独立窗口: 每次新建, 不复用; toast/banner 按活跃数堆叠偏移"""
        cls = self._STYLES[style]
        if style in ('toast', 'banner'):
            # 数量/高度限制: 超限淘汰最旧同 style 窗口, 保持堆叠可控
            same = [w for w in self._unique_windows
                    if getattr(w, '_notify_style', None) == style
                    and w.winfo_exists()]
            # 数量限制: 超过 _MAX_STACK 个 → 淘汰最旧
            while len(same) >= _MAX_STACK:
                same[0].destroy()  # _popup_closed 自动清理
                same = same[1:]
            # 总高度限制: 累计 (含复用窗口) 超过屏幕 _MAX_STACK_RATIO → 淘汰最旧
            max_h = int(self.root.winfo_screenheight() * _MAX_STACK_RATIO) \
                if self.root is not None else 0
            if max_h:
                h_used = sum(w.winfo_height() for w in same)
                # 复用窗口按 style:position 分键, 遍历匹配 (get(style) 已失效)
                prefix = style + ':'
                h_used += sum(p.winfo_height() for k, p in self._popups.items()
                              if k.startswith(prefix) and p.winfo_exists())
                while same and h_used > max_h:
                    old = same[0]
                    h_used -= old.winfo_height()  # 先取高度再销毁
                    old.destroy()
                    same = same[1:]
        if style == 'popup':
            kw.setdefault('grab', False)  # 多 popup 不互抢模态
        popup = None
        try:
            popup = cls(self, text, **kw)
            popup._notify_style = style
            self._unique_windows.append(popup)
            self.app.emit('app@window:set-icon', popup)
            self._reflow(style)  # 新窗口排入同 position 链 (同一事件循环, 无闪烁)
        except Exception:
            if popup is not None:
                try:
                    popup.destroy()
                except Exception:
                    pass
            raise

    def _popup_closed(self, popup):
        """通知窗口销毁后清理引用并重排补位 (由 _NotifyBase.destroy 回调)"""
        style = getattr(popup, '_notify_style', None)
        key = getattr(popup, '_popup_key', None)
        if popup in self._unique_windows:
            self._unique_windows.remove(popup)
        elif key and self._popups.get(key) is popup:
            self._popups.pop(key, None)
        else:
            for k, p in list(self._popups.items()):
                if p is popup:
                    self._popups.pop(k, None)
                    break
        if style:
            self._reflow(style)  # 后方窗口补位

    # -- public API --
    def _t(self, zh, en):
        """Return the localised string."""
        try:
            return zh if self.app.current_lang_name == 'zh' else en
        except Exception:
            return zh

    def _toast(self, text=None, **kw):
        if text is None:
            text = self._t('新通知', 'Notice')
        self._show('toast', text, **kw)

    def _popup(self, text=None, **kw):
        if text is None:
            text = self._t('通知', 'Notification')
        kw.setdefault('title', self._t('通知', 'Notification'))
        self._show('popup', text, **kw)

    def _banner(self, text=None, **kw):
        if text is None:
            text = self._t('新消息', 'Heads up')
        self._show('banner', text, **kw)

    def _canvas(self, text=None, **kw):
        if text is None:
            text = self._t('你好！', 'Hello!')
        self._show('canvas', text, **kw)

    def on_stop(self):
        if self.root is not None:
            try:
                self.root.unbind(self._WAKEUP_EVENT)
            except Exception:
                pass
        for popup in (list(self._popups.values())
                      + list(self._unique_windows)):
            try:
                popup.destroy()
            except Exception:
                pass
        self._popups.clear()
        self._unique_windows.clear()

    # -- Agent ---------------------------------------------------------
    
    def register_agent_tools(self):
        # 惰性 import — 保持模块 standalone
        from plugins.ai_assistant.core.registry import registry as agent_registry
        agent_registry.register('notify_operation', fn=self.agent_notify)

    def agent_notify(self,
        action: Literal['toast', 'popup', 'banner', 'canvas'],
        text: str = None,
        title: str = None,
        timeout: float = None,
        width: int = None,
        height: int = None,
        bg: str = None,
        fg: str = None,
        font_size: int = None,
        position: Literal['br', 'bl', 'tr', 'tl'] = None,
        pattern: Literal['flower', 'heart', 'star', 'sun',
                        'smiley'] = None,
        duration: int = None,
        x: int = None,
        y: int = None,
        show_time: bool = None,
        unique: bool = None):
        """
        发布系统通知: toast=角落滑出小卡片(轻量提示); popup=居中弹窗(点击关闭); banner=顶部全宽横幅; canvas=带图案的居中卡片

        action: 通知形式
        text: 正文, 省略用默认文案
        title: 窗口标题, 仅popup/canvas
        timeout: 自动关闭秒数, 0=不关闭; 省略用默认(toast 3秒, banner 5秒, popup/canvas不关闭)
        width: 宽度px, 省略自适应
        height: 高度px, 省略自适应
        bg: 背景色, 如#2b2b2b
        fg: 文字颜色, 如#ffffff
        font_size: 字体大小
        position: 弹出角落, 仅toast: br=右下(默认), bl=左下, tr=右上, tl=左上
        pattern: 图案, 仅canvas
        duration: 滑入动画毫秒, 仅toast/banner(默认300/400)
        x: 左上角横坐标px, 与y同用; popup/canvas默认居中
        y: 左上角纵坐标px
        show_time: 显示时间戳, 默认True
        unique: True=独立窗口堆叠, False=覆盖上一条(默认)
        """
        fn = {'toast': self._toast, 'popup': self._popup,
                'banner': self._banner, 'canvas': self._canvas}.get(action)
        if fn is None:
            return False
        kw = {
            'text': text, 'title': title, 'timeout': timeout,
            'width': width, 'height': height, 'bg': bg, 'fg': fg,
            'font_size': font_size, 'position': position,
            'pattern': pattern, 'duration': duration, 'x': x, 'y': y,
            'show_time': show_time, 'unique': unique}
        fn(**{k: v for k, v in kw.items() if v is not None})
        return True
    