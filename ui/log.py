# -*- coding: utf-8 -*-
"""Log window — same as parent project."""
import sys
import queue
import logging
import tkinter as tk
from common.state import AppState
from common.common import FONT_FAMILY, LOG_FMT, LOG_DATE_FMT, logger


class _LogRedirector:
    def __init__(self, original, log_queue):
        self.original = original
        self.queue = log_queue

    def write(self, text):
        if text:
            self.queue.put(text)
        if self.original is not None:
            self.original.write(text)
            self.original.flush()

    def flush(self):
        if self.original is not None:
            self.original.flush()


class LogUI(AppState, tk.Tk):

    def __init__(self):
        super().__init__()
        self._log_win = None
        self._log_queue = queue.Queue()
        self._log_buffer = []
        self._log_buffer_max = 2000
        self._log_redirector = _LogRedirector(sys.stdout, self._log_queue)
        sys.stdout = self._log_redirector
        sys.stderr = self._log_redirector
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(logging.Formatter(LOG_FMT, LOG_DATE_FMT))
        logger.addHandler(stream_handler)

    def init(self):
        super().init()
        self.on('window:open-log', self._show_log)
        self.on('theme:changed', lambda name: LogUI.apply_theme(self, name))
        self.on('lang:changed', lambda name: LogUI.apply_lang(self, name))

    def _show_log(self):
        if self._log_win is not None and self._log_win.winfo_exists():
            self._log_win.lift()
            self._log_win.focus_force()
            return
        t, l = self.theme, self.lang
        win = self.components.Toplevel(self)
        win.title(l['log_title'])
        win.resizable(True, True)
        self._log_win = win

        outer = self.components.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        border = self.components.Frame(
            outer, bg=t['border'], padx=1, pady=1)
        border.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._log_border_frame = border

        self._log_text = self.components.ScrollableText(
            border, wrap=tk.WORD, state=tk.DISABLED)
        self._log_text.pack(fill=tk.BOTH, expand=True)

        if self._log_buffer:
            self._log_text.configure(state=tk.NORMAL)
            chunk = 500
            for i in range(0, len(self._log_buffer), chunk):
                self._log_text.insert(
                    tk.END, ''.join(self._log_buffer[i:i + chunk]))
                self._log_text.update_idletasks()
            self._log_text.see(tk.END)
            self._log_text.configure(state=tk.DISABLED)

        self._log_bottom_frame = bottom = self.components.Frame(win)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 6))
        self._log_clear_btn = self.components.Button(
            bottom, text=l['log_clear'], command=self._clear_log,
            font=(FONT_FAMILY, 9, 'bold'))
        self._log_clear_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        self.emit('window:set-geometry', win, h=600)
        win.bind('<Destroy>', lambda _: self._on_log_win_closed())

    def _on_log_win_closed(self):
        self._log_win = None

    def poll_log_queue(self):
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._log_buffer.append(msg)
                if len(self._log_buffer) > self._log_buffer_max:
                    self._log_buffer = self._log_buffer[
                        -self._log_buffer_max:]
                if (self._log_win is not None
                        and self._log_win.winfo_exists()):
                    self._log_text.configure(state=tk.NORMAL)
                    self._log_text.insert(tk.END, msg)
                    self._log_text.see(tk.END)
                    self._log_text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self.poll_log_queue)

    def _clear_log(self):
        self._log_buffer = []
        if self._log_win is not None and self._log_win.winfo_exists():
            self._log_text.configure(state=tk.NORMAL)
            self._log_text.delete('1.0', tk.END)
            self._log_text.configure(state=tk.DISABLED)

    def apply_theme(self, name):
        if self._log_win is None or not self._log_win.winfo_exists():
            return
        t = self.theme
        self._log_win.config(bg=t['bg'])
        self._log_border_frame.config(bg=t['border'])
        self._log_text.config(bg=t['Text']['bg'], fg=t['Text']['fg'])
        self._log_bottom_frame.config(bg=t['bg'])
        if hasattr(self, '_log_clear_btn'):
            b = t['Button']
            self._log_clear_btn.config(
                bg=b['bg'], fg=b['fg'],
                activebackground=b['activebackground'],
                activeforeground=b['activeforeground'])

    def apply_lang(self, name):
        if self._log_win is None or not self._log_win.winfo_exists():
            return
        l = self.lang
        self._log_win.title(l['log_title'])
        if hasattr(self, '_log_clear_btn'):
            self._log_clear_btn.config(text=l['log_clear'])
