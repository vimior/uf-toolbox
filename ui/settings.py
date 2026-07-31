# -*- coding: utf-8 -*-
"""Settings window for tool/plugin paths."""
import tkinter as tk
from tkinter import filedialog, messagebox

from common.common import FONT_FAMILY
from common.state import AppState


class SettingsUI(AppState, tk.Tk):
    """Mixin that provides a settings window — opened via 'window:open-settings' event."""

    def init(self):
        super().init()
        self._settings_win = None
        self._settings_dirty = False
        self.on('window:open-settings', self._show_settings)
        self.on('theme:changed', lambda name: SettingsUI.apply_theme(self, name))
        self.on('lang:changed', lambda name: SettingsUI.apply_lang(self, name))

    # ---- theme / lang ----

    def apply_theme(self, name):
        if self._settings_win is None or not self._settings_win.winfo_exists():
            return
        t = self.theme
        win = self._settings_win
        win.configure(bg=t['bg'])

        w = self._config_widgets
        w['frame'].config(bg=t['bg'])
        w['bottom'].config(bg=t['bg'])

        for key in ('tool_lbl', 'plugin_lbl', 'repo_lbl'):
            w[key].config(bg=t['bg'], fg=t['fg'])

        for key in ('row1', 'row2', 'row3'):
            w[key].config(bg=t['bg'])

        for key in ('tool_entry', 'plugin_entry', 'repo_entry'):
            w[key].config(bg=t['input_bg'], fg=t['fg'],
                          insertbackground=t['fg'],
                          highlightbackground=t['separator'])

        for key in ('tool_btn', 'plugin_btn'):
            w[key].config(bg=t['menu_bg'], fg=t['fg'],
                          activebackground=t['btn_hover_bg'],
                          activeforeground=t['menu_hover_fg'])

        # Save button: respect dirty state
        if self._settings_dirty:
            w['save_btn'].config(bg=t['accent'], fg=t['btn_fg'],
                                 activebackground=t['btn_active_bg'],
                                 activeforeground=t['btn_fg'])
        else:
            w['save_btn'].config(bg=t['btn_disabled_bg'], fg=t['btn_fg'],
                                 activebackground=t['btn_active_bg'],
                                 activeforeground=t['btn_fg'])

    def apply_lang(self, name):
        if self._settings_win is None or not self._settings_win.winfo_exists():
            return
        l = self.lang
        self._settings_win.title(l['config_title'])
        w = self._config_widgets
        w['tool_lbl'].config(text=l['config_tool_path'])
        w['plugin_lbl'].config(text=l['config_plugin_path'])
        w['repo_lbl'].config(text=l['config_repo_url'])
        w['tool_btn'].config(text=l['config_select'])
        w['plugin_btn'].config(text=l['config_select'])
        w['save_btn'].config(text=l['config_save'])
        # self.emit('window:set-geometry', self._settings_win, h=200)

    # ---- window ----

    def _show_settings(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return

        l = self.lang
        t = self.theme

        win = tk.Toplevel(self)
        win.geometry('+{}+{}'.format(-9999, -9999))
        self.emit('window:set-icon', win)
        win.title(l['config_title'])
        win.resizable(False, False)
        win.configure(bg=t['bg'])
        self._settings_win = win

        w = {}  # widget refs for apply_theme / apply_lang

        # --- Content frame ---
        frame = tk.Frame(win, bg=t['bg'], padx=12, pady=12)
        frame.pack(fill=tk.BOTH, expand=True)
        w['frame'] = frame

        # Tool path
        tool_lbl = tk.Label(frame, text=l['config_tool_path'], bg=t['bg'],
                            fg=t['fg'], font=(FONT_FAMILY, 10), anchor=tk.W)
        tool_lbl.pack(fill=tk.X)
        w['tool_lbl'] = tool_lbl

        row1 = tk.Frame(frame, bg=t['bg'])
        row1.pack(fill=tk.X, pady=(2, 8))
        w['row1'] = row1

        tool_var = tk.StringVar(value=self.tool_path)
        self._orig_tool = self.tool_path
        tool_entry = tk.Entry(row1, textvariable=tool_var, bg=t['input_bg'],
                              fg=t['fg'], insertbackground=t['fg'],
                              font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                              highlightthickness=1, highlightbackground=t['separator'])
        tool_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        w['tool_entry'] = tool_entry

        tool_btn = tk.Button(row1, text=l['config_select'], bg=t['menu_bg'],
                             fg=t['fg'], font=(FONT_FAMILY, 9),
                             relief=tk.FLAT, padx=10, cursor='hand2', bd=0,
                             activebackground=t['btn_hover_bg'],
                             activeforeground=t['menu_hover_fg'],
                             command=lambda: self._pick_folder(tool_var))
        tool_btn.pack(side=tk.RIGHT, padx=(6, 0), ipady=1)
        w['tool_btn'] = tool_btn

        # Plugin path
        plugin_lbl = tk.Label(frame, text=l['config_plugin_path'], bg=t['bg'],
                              fg=t['fg'], font=(FONT_FAMILY, 10), anchor=tk.W)
        plugin_lbl.pack(fill=tk.X)
        w['plugin_lbl'] = plugin_lbl

        row2 = tk.Frame(frame, bg=t['bg'])
        row2.pack(fill=tk.X, pady=(2, 8))
        w['row2'] = row2

        plugin_var = tk.StringVar(value=self.plugin_path)
        self._orig_plugin = self.plugin_path
        plugin_entry = tk.Entry(row2, textvariable=plugin_var, bg=t['input_bg'],
                                fg=t['fg'], insertbackground=t['fg'],
                                font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                                highlightthickness=1, highlightbackground=t['separator'])
        plugin_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        w['plugin_entry'] = plugin_entry

        plugin_btn = tk.Button(row2, text=l['config_select'], bg=t['menu_bg'],
                               fg=t['fg'], font=(FONT_FAMILY, 9),
                               relief=tk.FLAT, padx=10, cursor='hand2', bd=0,
                               activebackground=t['btn_hover_bg'],
                               activeforeground=t['menu_hover_fg'],
                               command=lambda: self._pick_folder(plugin_var))
        plugin_btn.pack(side=tk.RIGHT, padx=(6, 0), ipady=1)
        w['plugin_btn'] = plugin_btn

        # Repo URL
        repo_lbl = tk.Label(frame, text=l['config_repo_url'], bg=t['bg'],
                             fg=t['fg'], font=(FONT_FAMILY, 10), anchor=tk.W)
        repo_lbl.pack(fill=tk.X)
        w['repo_lbl'] = repo_lbl

        row3 = tk.Frame(frame, bg=t['bg'])
        row3.pack(fill=tk.X, pady=(2, 8))
        w['row3'] = row3

        repo_var = tk.StringVar(value=self.repo_url)
        self._orig_repo = self.repo_url
        repo_entry = tk.Entry(row3, textvariable=repo_var, bg=t['input_bg'],
                               fg=t['fg'], insertbackground=t['fg'],
                               font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                               highlightthickness=1, highlightbackground=t['separator'])
        repo_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        w['repo_entry'] = repo_entry

        # --- Save button at bottom ---
        bottom = tk.Frame(win, bg=t['bg'])
        bottom.pack(fill=tk.X, padx=8, pady=(0, 6))
        w['bottom'] = bottom

        save_btn = tk.Button(
            bottom, text=l['config_save'],
            command=lambda: self._save_config_fields(
                tool_var.get().strip(), plugin_var.get().strip(),
                repo_var.get().strip(), win),
            bg=t['btn_disabled_bg'], fg=t['btn_fg'],
            font=(FONT_FAMILY, 9, 'bold'),
            relief=tk.RAISED, bd=1, padx=8, pady=1, cursor='hand2',
            activebackground=t['btn_active_bg'],
            activeforeground=t['btn_fg'],
            state=tk.DISABLED)
        save_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        w['save_btn'] = save_btn

        self._config_widgets = w

        # --- Change tracking ---
        self._settings_dirty = False

        def _check_dirty(*args):
            cur_tool = tool_var.get().strip()
            cur_plugin = plugin_var.get().strip()
            cur_repo = repo_var.get().strip()
            is_dirty = (cur_tool != self._orig_tool
                        or cur_plugin != self._orig_plugin
                        or cur_repo != self._orig_repo)
            if is_dirty and not self._settings_dirty:
                self._settings_dirty = True
                save_btn.config(bg=t['accent'], state=tk.NORMAL,
                                activebackground=t['btn_active_bg'])
            elif not is_dirty and self._settings_dirty:
                self._settings_dirty = False
                save_btn.config(bg=t['btn_disabled_bg'], state=tk.DISABLED)

        tool_var.trace('w', _check_dirty)
        plugin_var.trace('w', _check_dirty)
        repo_var.trace('w', _check_dirty)

        # --- Close guard ---
        def _on_close():
            cur_tool = tool_var.get().strip()
            cur_plugin = plugin_var.get().strip()
            cur_repo = repo_var.get().strip()
            if (cur_tool != self._orig_tool
                    or cur_plugin != self._orig_plugin
                    or cur_repo != self._orig_repo):
                answer = messagebox.askyesnocancel(
                    l['config_title'], l['config_unsaved_msg'])
                if answer is None:
                    return
                if answer:
                    self._save_config_fields(cur_tool, cur_plugin, cur_repo, win)
                    return
            win.destroy()

        win.protocol('WM_DELETE_WINDOW', _on_close)
        win.bind('<Destroy>', lambda _: self._on_config_win_closed())

        self.emit('window:set-geometry', win, h=260)
        # win.lift()
        # win.focus_force()

    def _on_config_win_closed(self):
        self._settings_win = None
        self._settings_dirty = False

    @staticmethod
    def _pick_folder(var):
        path = filedialog.askdirectory(title='Select Folder')
        if path:
            var.set(path)

    def _save_config_fields(self, tool_path, plugin_path, repo_url, win):
        """保存配置字段并关闭窗口（避免与 AppState._save_config 重名冲突）。"""
        self._config['tool_path'] = tool_path
        self._config['plugin_path'] = plugin_path
        self._config['repo_url'] = repo_url
        self._save_config()
        win.destroy()
