# -*- coding: utf-8 -*-
"""UF Toolbox — plugin-host application."""
import os
import sys
import tkinter as tk

from ui.menu import MenuUI
from ui.log import LogUI
from ui.config import ConfigUI
from plugins.base import load_plugins
from tools.scanner import kill_all


class UFToolBox(MenuUI, LogUI, ConfigUI, tk.Tk):
    """Plugin-host application with MRO-based architecture."""

    def __init__(self):
        super().__init__()
        self.init_state()
        self.withdraw()
        self.title("UF Toolbox")
        self.overrideredirect(True)
        self.resizable(True, False)
        self.configure(bg=self.theme['bg'])

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
        kill_all()
        super().destroy()

    # ---- plugin loading ----

    def init(self):
        super().init()
        self.on('set-win-position', self._set_window_position)
        self.on('set-win-icon', self._set_window_icon)
        self.on('load-plugins', self._load_plugins)

    def _set_window_position(self, win, w=None, h=400):
        # x = self.winfo_x() - 8 + self.winfo_width() + 4
        # y = self.winfo_y()
        # w = w
        # h = h or self.main_height

        x = self.winfo_x() - 3
        # y = self.winfo_y() + self.winfo_height() + 1
        y = self.winfo_y() + self.main_height + 1
        if not w:
            w = self.main_width
        else:
            x = x + (self.main_width - w) // 2
        w = w or self.main_width
        h = h or self.main_height
        win.geometry('{}x{}+{}+{}'.format(w, h, x, y))

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
                icon = tk.PhotoImage(file=path)
                win.iconphoto(True, icon)
                win._icon_ref = icon
            except Exception:
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(path)
                    icon = ImageTk.PhotoImage(img)
                    win.iconphoto(True, icon)
                    win._icon_ref = icon
                except Exception:
                    pass

    def _load_plugins(self):
        if getattr(sys, 'frozen', False):
            plugin_dirs = [os.path.join(sys._MEIPASS, 'plugins')]
            base = os.path.dirname(sys.executable)
            plugin_path = os.path.join(base, 'plugins')
            if os.path.isdir(plugin_path):
                if base not in sys.path:
                    sys.path.insert(0, base)
                if plugin_path not in plugin_dirs:
                    plugin_dirs.append(plugin_path)
            if self.plugin_path and self.plugin_path != 'plugins':
                plugin_path = os.path.join(base, self.plugin_path)
                if os.path.isdir(plugin_path):
                    root = os.path.dirname(plugin_path)
                    if root not in sys.path:
                        sys.path.insert(0, root)
                    if plugin_path not in plugin_dirs:
                        plugin_dirs.append(plugin_path)
        else:
            base = os.path.dirname(os.path.abspath(__file__))
            plugin_dirs = [
                os.path.join(base, 'plugins'),
                os.path.join(base, 'dist', 'plugins'),
            ]
            if self.plugin_path and self.plugin_path != 'tools':
                plugin_dirs.append(os.path.join(base, 'dist', self.plugin_path))
        load_plugins(self, self.plugins, plugin_dirs)


# ================================================================
#  Entry point
# ================================================================
def main():
    toolbox = UFToolBox()
    toolbox.mainloop()


if __name__ == '__main__':
    main()
