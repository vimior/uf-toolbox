# -*- coding: utf-8 -*-
"""UF Toolbox — plugin-host application."""
import os
import sys
import tkinter as tk
from tkinter import messagebox
from ui.menu import MenuUI
from ui.log import LogUI
from ui.settings import SettingsUI
from ui.about import AboutUI


class UFToolBox(MenuUI, LogUI, SettingsUI, AboutUI, tk.Tk):
    """Plugin-host application with MRO-based architecture."""

    def __init__(self):
        super().__init__()
        self.init_state()
        self.withdraw()
        self.title("UF Toolbox")
        self.overrideredirect(True)
        self.resizable(True, False)
        self.configure(bg=self.theme['bg'])
        self._icon = None

        self.init()

        # ---------- menu bar ----------
        self._build_menu()
        self._set_window_icon(self)

        # Apply topmost setting from config on startup
        self._apply_topmost(self.always_on_top)

        # ---------- data polling ----------
        self.after(100, self.poll_log_queue)

        self.resizable(True, False)
        self.deiconify()
        self.set_main_width(self.winfo_width())
        self.set_main_height(self.winfo_height())

        # Trigger initial auto-hide check 5s after startup
        self.after(5000, self._check_auto_hide)

    def destroy(self):
        self._tm.kill_all()
        super().destroy()

    def init(self):
        super().init()
        self.on('set-win-position', self._set_window_position)
        self.on('set-win-icon', self._set_window_icon)

    def _set_window_position(self, win, x=None, y=None, w=None, h=400, fixed_size=True, fixed_position=True):
        """Position/size a child window. None = use default or skip.

        No args: full defaults — right of main window, main_width x main_height.
        Explicit x/y/w/h override or extend the defaults.
        """
        def_x = self.winfo_x() - 3
        def_y = self.winfo_y() + self.main_height + 1
        def_w = self.main_width
        def_h = self.main_height

        parts = []
        if w is not None or h is not None:
            w = w or def_w
            h = h or def_h
            parts.append(f'{w}x{h}')
        elif fixed_size:
            parts.append(f'{def_w}x{def_h}')
        if x is not None or y is not None:
            x = x if x is not None else def_x
            y = y if y is not None else def_y
            if w and w != def_w:
                x = x + (def_w - w) // 2
            parts.append(f'+{x}+{y}')
        elif fixed_position:
            x = def_x
            if w and w != def_w:
                x = x + (def_w - w) // 2
            parts.append(f'+{x}+{def_y}')

        if not parts:
            win.geometry(f'{def_w}x{def_h}+{def_x}+{def_y}')
        else:
            win.geometry(''.join(parts))

    def _set_window_icon(self, win, ico_path=None, png_path=None):
        """Cross-platform window icon: iconphoto on Linux, iconbitmap on Windows."""
        _ico_path = self.ico_path if ico_path is None else ico_path
        _png_path = self.png_path if png_path is None else png_path
        if sys.platform == 'win32':
            try:
                win.iconbitmap(_ico_path)
            except Exception:
                pass
        else:
            # Try tk.PhotoImage first (no PIL dependency), fall back to PIL
            path = _png_path if _png_path and os.path.exists(_png_path) else _ico_path
            try:
                if self._icon is None:
                    self._icon = tk.PhotoImage(file=path)
                win.iconphoto(True, self._icon)
                win._icon_ref = self._icon
            except Exception:
                try:
                    if self._icon is None:
                        from PIL import Image, ImageTk
                        img = Image.open(path)
                        icon = ImageTk.PhotoImage(img)
                    win.iconphoto(True, self._icon)
                    win._icon_ref = self._icon
                except Exception:
                    pass


# ================================================================
#  Single-instance guard
# ================================================================
_MUTEX_NAME = 'Global\\UF_Toolbox_SingleInstance'


def _lock_instance():
    """Acquire single-instance lock. Returns True if this is the only instance."""
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.kernel32.CreateMutexW(None, False, _MUTEX_NAME)
        return ctypes.windll.kernel32.GetLastError() != 183  # 183 = ERROR_ALREADY_EXISTS
    else:
        import fcntl
        _lock_path = os.path.join(os.path.expanduser('~'), '.uf_toolbox.lock')
        _lock_fp = open(_lock_path, 'w')
        try:
            fcntl.lockf(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_fp.write(str(os.getpid()))
            _lock_fp.flush()
            return True
        except (IOError, OSError):
            return False


# ================================================================
#  Entry point
# ================================================================
def main():
    if not _lock_instance():
        # Determine language from system locale
        try:
            import locale
            loc = locale.getdefaultlocale()[0]
            is_zh = loc and loc.startswith('zh')
        except Exception:
            is_zh = False
        msg = '程序已在运行中，请勿重复启动。' if is_zh else 'Application is already running.'

        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo('UF Toolbox', msg)
        root.destroy()
        sys.exit(1)
    toolbox = UFToolBox()
    toolbox.mainloop()


if __name__ == '__main__':
    main()
