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
        win = tk.Toplevel(self)
        win.geometry('+{}+{}'.format(-9999, -9999))
        self.emit('window:set-icon', win)
        win.title(l['log_title'])
        win.configure(bg=t['bg'])
        win.resizable(True, True)
        self._log_win = win

        outer = tk.Frame(win, bg=t['bg'])
        outer.pack(fill=tk.BOTH, expand=True, padx=(8, 0), pady=(8, 4))

        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL,
                                 width=12, relief=tk.FLAT,
                                 borderwidth=0, bg=t['scroll_bar'], troughcolor=t['scroll_frame'])
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._log_border_frame = border = tk.Frame(
            outer, bg=t['border'], padx=1, pady=1,
            bd=0, highlightthickness=0)
        border.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._log_text = tk.Text(
            border, wrap=tk.WORD,
            bg='#1e1e1e', fg='#d4d4d4', insertbackground='white',
            font=('Consolas', 9), relief=tk.FLAT,
            state=tk.DISABLED, padx=6, pady=4,
            highlightbackground='#1e1e1e', highlightcolor='#1e1e1e',
            yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._log_text.yview)
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

        self._log_bottom_frame = bottom = tk.Frame(win, bg=t['bg'])
        bottom.pack(fill=tk.X, padx=8, pady=(0, 6))
        self._log_clear_btn = tk.Button(
            bottom, text=l['log_clear'], command=self._clear_log,
            bg=t['accent'], fg=t['btn_fg'],
            font=(FONT_FAMILY, 9, 'bold'),
            relief=tk.RAISED, bd=1, padx=8, pady=1, cursor='hand2',
            activebackground=t['btn_active_bg'],
            activeforeground=t['btn_fg']
        )
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
        self._log_bottom_frame.config(bg=t['bg'])
        if hasattr(self, '_log_clear_btn'):
            self._log_clear_btn.config(
                bg=t['accent'], fg=t['btn_fg'],
                activebackground=t['btn_active_bg'],
                activeforeground=t['btn_fg'])

    def apply_lang(self, name):
        if self._log_win is None or not self._log_win.winfo_exists():
            return
        l = self.lang
        self._log_win.title(l['log_title'])
        if hasattr(self, '_log_clear_btn'):
            self._log_clear_btn.config(text=l['log_clear'])
        self.emit('window:set-geometry', self._log_win, h=600)
