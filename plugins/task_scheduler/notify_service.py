# -*- coding: utf-8 -*-
"""Notification service — ServicePlugin, provides popup notifications.

Services for other plugins / task callbacks:
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
import sys
import math
import time
import tkinter as tk

from plugins.plugin import ServicePlugin

# ---------------------------------------------------------------------------
# flower petal colours (shared)
# ---------------------------------------------------------------------------
_PETAL_COLORS = ('#ff6b8a', '#ff8fab', '#ffb3c6', '#ff6b8a',
                 '#ff8fab', '#ffb3c6', '#ff6b8a', '#ff8fab')


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
                 bg='#2b2b2b', fg='#ffffff', font_size=10,
                 time_font_size=9, time_fg=None):
        super().__init__(owner.root)
        self.geometry('+30000+30000')  # park far off-screen during build
        self.update_idletasks()  # force the geometry to take effect
        self.withdraw()
        self._owner = owner
        self._components = getattr(owner, 'components', tk)
        self._timeout = self._i(timeout)
        self._timer_id = None
        self._show_time = self._parse_show_time(show_time)
        self._bg = bg
        self._fg = fg
        self._font_size = font_size
        self._time_font_size = time_font_size
        self._time_fg = time_fg
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
        """Override in subclasses."""

    def destroy(self):
        if self._timer_id is not None:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        super().destroy()

    def refresh(self, text='', timeout=None, **kw):
        """Override in subclasses to update content and reset timer."""
        if 'show_time' in kw:
            self._show_time = self._parse_show_time(kw['show_time'])
        if 'bg' in kw:
            self._bg = kw['bg']
        if 'fg' in kw:
            self._fg = kw['fg']
        if 'font_size' in kw:
            self._font_size = kw['font_size']
        if 'time_font_size' in kw:
            self._time_font_size = kw['time_font_size']
        if 'time_fg' in kw:
            self._time_fg = kw['time_fg']
        if text:
            self._apply_text(text)
        self._apply_style()
        self._refresh_time_label()
        if 'width' in kw or 'height' in kw:
            w = self._i(kw.get('width', 0), 0) or self.winfo_width()
            h = self._i(kw.get('height', 0), 0) or self.winfo_height()
            self._apply_geometry(w, h)
        if 'x' in kw and 'y' in kw:
            self._apply_position(self._i(kw['x']), self._i(kw['y']))
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

    _POS = {
        'br': (1.0, 1.0, 's', -1),   # bottom-right → slide up
        'bl': (0.0, 1.0, 's', -1),   # bottom-left  → slide up
        'tr': (1.0, 0.0, 'n', -1),   # top-right    → slide down
        'tl': (0.0, 0.0, 'n', -1),   # top-left     → slide down
    }

    def __init__(self, owner, text=None, timeout=3, duration=300,
                 position='br', bg='#333333', fg='#ffffff',
                 font_size=10, width=0, height=0,
                 x=None, y=None, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=_kw.pop('time_font_size', 8),
                         time_fg=_kw.pop('time_fg', None))
        self.overrideredirect(True)
        self.attributes('-topmost', True)

        self._duration = self._i(duration, 300)

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

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = _w if _w > 0 else self.winfo_reqwidth()
        h = _h if _h > 0 else self.winfo_reqheight()

        # calculate target position
        if x is not None and y is not None:
            tx, ty = _x, _y
            start_dir = 's' if ty > sh / 2 else 'n'
        else:
            rx, ry, _anchor, start_dir = self._POS.get(position, self._POS['br'])
            # bottom margin 50px to clear taskbar, top/side 12px
            bm = 50 if ry > 0.5 else 12
            tm = 12
            tx = int((sw - w) * rx) - (tm if rx > 0.5 else -tm)
            ty = int((sh - h) * ry) - bm

        if start_dir == 's':
            start_y = sh
        else:
            start_y = -h

        self.geometry(f'{w}x{h}+{tx}+{start_y}')
        self.deiconify()
        self._animate_in(tx, ty, 0)

    def _animate_in(self, tx, ty, step):
        step += 1
        total = max(1, int(self._duration / 10))
        progress = min(1.0, step / total)
        # ease-out: 1 - (1-t)^2
        eased = 1 - (1 - progress) ** 2
        cy = int(ty + (1 - eased) * (self.winfo_y() - ty))
        self.geometry(f'+{tx}+{cy}')
        if step < total:
            self.after(10, lambda: self._animate_in(tx, ty, step))

    def _on_click(self):
        self._timeout = 3
        self._reset_timer()

    def refresh(self, text='', timeout=None, **kw):
        if 'position' in kw:
            rx, ry, _, _ = self._POS.get(kw['position'], self._POS['br'])
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            bm = 50 if ry > 0.5 else 12
            tm = 12
            tx = int((sw - self.winfo_width()) * rx) - (tm if rx > 0.5 else -tm)
            ty = int((sh - self.winfo_height()) * ry) - bm
            self.geometry(f'+{tx}+{ty}')
        super().refresh(text, timeout, **kw)

    def destroy(self):
        self.attributes('-topmost', False)
        super().destroy()


# ===================================================================
# Popup — centred dialog
# ===================================================================

class _Popup(_NotifyBase):
    """Centred dialog — click anywhere to dismiss."""

    def __init__(self, owner, text=None, title=None, timeout=0,
                 width=360, height=200, bg='#2b2b2b', fg='#e0e0e0',
                 font_size=10, x=None, y=None, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=_kw.pop('time_font_size', 9),
                         time_fg=_kw.pop('time_fg', None))
        self.resizable(False, False)

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
        self.grab_set()
        self.focus_set()

    def refresh(self, text='', timeout=None, **kw):
        if 'title' in kw:
            self.title(kw['title'])
        super().refresh(text, timeout, **kw)


# ===================================================================
# Banner — top-of-screen slide-down strip
# ===================================================================

class _Banner(_NotifyBase):
    """Full-width banner that slides down from the top of the screen."""

    def __init__(self, owner, text=None, timeout=5, duration=400,
                 bg='#2d5a8a', fg='#ffffff', font_size=11,
                 width=0, height=0, **_kw):
        super().__init__(owner, timeout, bg=bg, fg=fg, font_size=font_size,
                         show_time=_kw.pop('show_time', True),
                         time_font_size=_kw.pop('time_font_size', 9),
                         time_fg=_kw.pop('time_fg', None))
        self.overrideredirect(True)
        self.attributes('-topmost', True)
        self._duration = self._i(duration, 400)

        if text is None:
            text = ''

        sw = self.winfo_screenwidth()
        _bw = self._i(width)
        bw = _bw if _bw > 0 else sw

        self._frame = self._components.Frame(self, bg=self._bg, padx=20, pady=8)
        self._frame.pack(fill=tk.BOTH, expand=True)
        self._label = self._components.Label(self._frame, text=text,
                               font=(FONT_FAMILY, self._font_size),
                               bg=self._bg, fg=self._fg,
                               anchor='center', justify=tk.CENTER)
        self._label.pack(fill=tk.BOTH, expand=True)

        self._time_label = self._components.Label(self._frame, text='',
                                     font=self._components.mono_font(self._time_font_size),
                                     bg=self._bg, fg=self._fg)
        self._refresh_time_label()

        self.update_idletasks()
        _bh = self._i(height)
        h = _bh if _bh > 0 else self.winfo_reqheight()
        bx = (sw - bw) // 2
        self.geometry(f'{bw}x{h}+{bx}+{-h}')
        self.deiconify()
        self._animate_in(bx, 0)

    def _animate_in(self, bx, step):
        step += 1
        total = max(1, int(self._duration / 10))
        progress = min(1.0, step / total)
        eased = 1 - (1 - progress) ** 2
        y = int(-self.winfo_reqheight() * (1 - eased))
        self.geometry(f'+{bx}+{y}')
        if step < total:
            self.after(10, lambda bx=bx, s=step: self._animate_in(bx, s))

    def _on_click(self):
        self._timeout = 3
        self._reset_timer()

    def destroy(self):
        self.attributes('-topmost', False)
        super().destroy()


# ===================================================================
# Canvas — decorative popup with multiple drawing patterns
# ===================================================================

class _Canvas(_NotifyBase):
    """Decorative canvas popup with multiple drawing patterns."""

    _PATTERNS = ('flower', 'heart', 'star', 'sun', 'smiley')

    _TITLES = {'flower': '🌸', 'heart': '❤️', 'star': '⭐', 'sun': '☀️', 'smiley': '😊'}
    _SIZES = {'flower': (300, 360), 'heart': (280, 300),
              'star': (280, 300), 'sun': (300, 310), 'smiley': (280, 300)}

    def __init__(self, owner, text=None, timeout=0, title=None, pattern='flower',
                 width=None, height=None, bg='#1a1a2e', fg='#f0e68c',
                 font_size=13, x=None, y=None, time_font_size=9,
                 time_fg='#888888', **_kw):
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
        if text:
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
        # Pop x/y before super (Canvas uses OR logic, base uses AND)
        if 'x' in kw or 'y' in kw:
            px = self._i(kw.pop('x', None), None)
            py = self._i(kw.pop('y', None), None)
            if px is not None and py is not None:
                self.geometry(f'+{px}+{py}')
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

    def __init__(self, app=None):
        super().__init__(app)
        self._popups = {}  # style -> _NotifyBase instance

        s = self.services
        s.register('toast', self._toast)
        s.register('popup', self._popup)
        s.register('banner', self._banner)
        s.register('canvas', self._canvas)

    # -- helpers --
    _STYLES = {'toast': _Toast, 'popup': _Popup,
               'banner': _Banner, 'canvas': _Canvas}

    def _show(self, style, text, **kw):
        popup = self._popups.get(style)
        if popup and popup.winfo_exists():
            popup.refresh(text, **kw)
            return
        cls = self._STYLES[style]
        popup = None
        try:
            popup = cls(self, text, **kw)
            self._popups[style] = popup
            self.app.emit('app@window:set-icon', popup)
        except Exception:
            if popup is not None:
                try:
                    popup.destroy()
                except Exception:
                    pass
            raise  # re-raise so the task engine marks the task as failed

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
        for popup in list(self._popups.values()):
            try:
                popup.destroy()
            except Exception:
                pass
        self._popups.clear()
