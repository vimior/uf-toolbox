# -*- coding: utf-8 -*-
"""Plugin Manager — browse, install & manage plugins."""
import os
import sys
import queue
import shutil
import threading
import time
import tkinter as tk

from plugins.plugin import GuiPlugin
from .repo import PluginRepo, PluginRepoError

if sys.platform == 'win32':
    FONT_FAMILY = 'Microsoft YaHei'
elif sys.platform == 'darwin':
    FONT_FAMILY = 'PingFang SC'
else:
    FONT_FAMILY = 'Ubuntu'

_LANG = {
    'zh': {
        'title':          '插件管理器',
        'loading':        '加载中...',
        'load_failed':    '加载失败',
        'no_plugins':     '暂无可用插件',
        'plugin_count':   '共 {} 个插件',
        'refresh':        '刷新',
        'install':        '安装',
        'installing':     '安装中...',
        'update_to':       '更新到 v{}',
        'current':        '已安装',
        'local_plugin':   '本地插件',
        'orphan':         '未在插件商店中',
        'updated_at':     '上次刷新: {}',
        'never':          '从未刷新',
        'retry':          '重试',
        'network_error':  '网络错误，请检查连接后重试',
        'size_kb':        '{} KB',
        'downloading':    '下载中 {}%',
        'extracting':     '解压中...',
        'back':           '返回列表',
        'install_done':   '安装完成',
        'install_failed': '安装失败',
        'confirm_title':  '确认安装',
        'confirm_install': '确定要安装 "{}" 吗 ?',
        'confirm_update':  '确定要将 "{}" 从 v{} 更新到 v{} 吗 ?',
        'confirm_overwrite': '检测到本地已有 "{}", 确定要覆盖安装 v{} 吗 ?\n\n(覆盖后可在插件商店中正常更新)',
        'filter_remote': '远程',
        'filter_local':  '本地',
        'delete':        '删除',
        'delete_confirm': '确定要删除 "{}" v{} 吗 ?\n\n可通过插件商店重新安装恢复。',
        'delete_confirm_orphan': '⚠️ "{}" 是本地插件, 删除后无法通过插件商店恢复！\n\n确定要删除吗 ?',
        'delete_done':   '已删除',
        'local_ver':     '本地版本',
        'ok':            '确定',
        'cancel':        '取消',
    },
    'en': {
        'title':          'Plugin Manager',
        'loading':        'Loading...',
        'load_failed':    'Load Failed',
        'no_plugins':     'No plugins available',
        'plugin_count':   '{} plugin(s)',
        'refresh':        'Refresh',
        'install':        'Install',
        'installing':     'Installing...',
        'update_to':       'Update to v{}',
        'current':        'Installed',
        'local_plugin':   'Local Plugin',
        'orphan':         'Not in Store',
        'updated_at':     'Last refresh: {}',
        'never':          'Never',
        'retry':          'Retry',
        'network_error':  'Network error, check connection and retry',
        'size_kb':        '{} KB',
        'downloading':    'Downloading {}%',
        'extracting':     'Extracting...',
        'back':           'Back',
        'install_done':   'Installation complete',
        'install_failed': 'Installation failed',
        'confirm_title':  'Confirm',
        'confirm_install': 'Install "{}"?',
        'confirm_update':  'Update "{}" from v{} to v{}?',
        'confirm_overwrite': 'Local version of "{}" detected. Overwrite with v{}?\n\n(After overwriting, updates will be managed by the store.)',
        'filter_remote': 'Remote',
        'filter_local':  'Local',
        'delete':        'Delete',
        'delete_confirm': 'Delete "{}" v{}?\n\nCan be reinstalled from the store.',
        'delete_confirm_orphan': '⚠️ "{}" is a local plugin and cannot be restored after deletion!\n\nDelete it?',
        'delete_done':   'Deleted',
        'local_ver':     'Local Ver',
        'ok':            'OK',
        'cancel':        'Cancel',
    },
}

_STYLE = {
    'dark': {
        'bg':        '#2b2b2b',
        'bar_bg':    '#333333',
        'card_bg':   '#363636',
        'fg':        '#e0e0e0',
        'hint':      '#888888',
        'hover':     '#4a4a4a',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
        'btn_bg':    '#444444',
        'btn_fg':    '#e0e0e0',
        'success':   '#4caf50',
        'warn':      '#ff9800',
        'error':     '#f44336',
        'sep':       '#444444',
        'progress_bg': '#555555',
        'progress_fg': '#2d5a8a',
        'scroll_frame': '#252525',
        'scroll_bar':   '#333333',
    },
    'light': {
        'bg':        '#f5f5f5',
        'bar_bg':    '#e0e0e0',
        'card_bg':   '#ffffff',
        'fg':        '#333333',
        'hint':      '#999999',
        'hover':     '#d0d0d0',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
        'btn_bg':    '#e0e0e0',
        'btn_fg':    '#333333',
        'success':   '#388e3c',
        'warn':      '#f57c00',
        'error':     '#d32f2f',
        'sep':       '#cccccc',
        'progress_bg': '#e0e0e0',
        'progress_fg': '#2d5a8a',
        'scroll_frame': '#f5f5f5',
        'scroll_bar':   '#e0e0e0',
    },
}


class PluginStore(GuiPlugin):
    """插件管理器 — 浏览、安装、管理本地及远程插件"""

    name = "Plugin Manager"
    name_zh = "插件管理器"
    name_en = "Plugin Manager"
    namespace = "plugin_store"
    priority = 997
    reload = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        lang_name = self.app.current_lang_name
        theme_name = self.app.current_theme_name
        self._lbl = _LANG.get(lang_name, _LANG['en'])
        self._s = _STYLE.get(theme_name, _STYLE['dark'])
        s = self._s

        self.title(self._lbl['title'])
        self.geometry("520x600")
        self.resizable(True, True)
        self.configure(bg=s['bg'])

        # ---- 状态 ----
        self._remote_plugins = []   # 远程插件列表
        self._installed = {}        # 本地已安装信息
        self._base_url = ''         # 远程配置 base URL
        self._fetch_error = None    # 最近一次 fetch 错误
        self._cards = []            # 当前渲染的卡片 (frame, info, status)
        self._install_thread = None
        self._fetching = False      # 是否正在 fetch 中
        self._loaded = False        # 是否已成功加载过 (区分初始态与错误态)
        self._last_refresh = None
        self._result_queue = queue.Queue()  # 线程结果队列
        self._poll_id = None                # after ID for polling
        self._last_filter = 'both'          # 上次筛选状态: 'both'/'remote'/'local'
        self._filter_changing = False       # 防止 set() 触发递归
        self._destroyed = False             # 已销毁标记

        # ---- 顶部工具栏 ----
        bar = tk.Frame(self, bg=s['bar_bg'], height=36)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        title_lbl = tk.Label(bar, text=self._lbl['title'], bg=s['bar_bg'],
                             fg=s['fg'], font=(FONT_FAMILY, 11, 'bold'))
        title_lbl.pack(side=tk.LEFT, padx=12, pady=6)

        # 远程/本地筛选复选框
        self._show_remote_var = tk.BooleanVar(value=True)
        self._show_local_var = tk.BooleanVar(value=True)
        cb_remote = tk.Checkbutton(bar, text=self._lbl['filter_remote'],
                                   variable=self._show_remote_var,
                                   command=self._on_filter_change,
                                   bg=s['bar_bg'], fg=s['fg'],
                                   selectcolor=s['bar_bg'],
                                   activebackground=s['bar_bg'],
                                   activeforeground=s['fg'],
                                   font=(FONT_FAMILY, 9))
        cb_remote.pack(side=tk.LEFT, padx=2, pady=6)
        cb_local = tk.Checkbutton(bar, text=self._lbl['filter_local'],
                                  variable=self._show_local_var,
                                  command=self._on_filter_change,
                                  bg=s['bar_bg'], fg=s['fg'],
                                  selectcolor=s['bar_bg'],
                                  activebackground=s['bar_bg'],
                                  activeforeground=s['fg'],
                                  font=(FONT_FAMILY, 9))
        cb_local.pack(side=tk.LEFT, padx=2, pady=6)

        refresh_btn = tk.Label(bar, text=' ↻ ' + self._lbl['refresh'],
                               bg=s['accent'], fg=s['accent_fg'],
                               font=(FONT_FAMILY, 9, 'bold'),
                               padx=12, pady=3, cursor='hand2',
                               relief=tk.FLAT)
        refresh_btn.pack(side=tk.RIGHT, padx=8, pady=4)
        refresh_btn.bind('<Button-1>', lambda e: self._on_refresh())
        refresh_btn.bind('<Enter>',
                         lambda e, b=refresh_btn: b.config(bg='#3a6fa8'))
        refresh_btn.bind('<Leave>',
                         lambda e, b=refresh_btn: b.config(bg=s['accent']))
        self._refresh_btn = refresh_btn

        # 分隔线
        tk.Frame(self, bg=s['sep'], height=1).pack(fill=tk.X, side=tk.TOP)

        # 错误提示条 (默认隐藏)
        self._error_banner = tk.Frame(self, bg='#5c2e2e')
        self._error_banner_lbl = tk.Label(
            self._error_banner, text='', bg='#5c2e2e', fg='#ffb4b4',
            font=(FONT_FAMILY, 9), anchor=tk.W)
        self._error_banner_lbl.pack(fill=tk.X, padx=12, pady=3)

        # ---- 可滚动卡片列表区域 ----
        canvas_frame = tk.Frame(self, bg=s['bg'])
        canvas_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        self._canvas = self.components.ScrollableCanvas(
            canvas_frame, bg=s['bg'], scrollbars='y')
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollable_frame = self._canvas.inner

        # ---- 底栏 ----
        bottom = tk.Frame(self, bg=s['bar_bg'], height=28)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)

        self._time_lbl = tk.Label(bottom, text=self._lbl['never'],
                                  bg=s['bar_bg'], fg=s['hint'],
                                  font=(FONT_FAMILY, 8))
        self._time_lbl.pack(side=tk.LEFT, padx=10, pady=4)

        # ---- 初始加载 ----
        self._show_loading()

    # ---- 生命周期 ----

    def on_show(self):
        if not self._loaded:
            self._fetch_plugin_list()

    def on_destroy(self):
        self._destroyed = True
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        # 清空队列
        try:
            while True:
                self._result_queue.get_nowait()
        except queue.Empty:
            pass

    # ---- 队列轮询 (主线程安全)  ----

    def _start_polling(self):
        """启动主线程轮询，每 100ms 检查结果队列"""
        if self._poll_id is not None:
            return

        def _poll():
            self._poll_id = None
            if getattr(self, '_destroyed', False):
                return
            try:
                while True:
                    msg = self._result_queue.get_nowait()
                    self._handle_queue_msg(msg)
            except queue.Empty:
                pass
            except Exception:
                import traceback
                traceback.print_exc()
            try:
                if self.winfo_exists():
                    self._poll_id = self.after(100, _poll)
            except Exception:
                pass

        self._poll_id = self.after(100, _poll)

    def _handle_queue_msg(self, msg):
        """主线程处理队列消息"""
        msg_type = msg.get('type')
        if msg_type == 'local_done':
            # 本地扫描先行完成 → 先渲染本地插件 (不阻塞远程 fetch)
            self._on_local_done(msg.get('installed'))
        elif msg_type == 'fetch_done':
            self._on_fetch_done(msg.get('data'))
        elif msg_type == 'install_done':
            self._on_install_done(msg.get('namespace'), msg.get('error'))

    # ---- 数据加载 ----

    def _fetch_plugin_list(self):
        """在线程中获取远程插件列表和本地扫描

        本地扫描先行 (不依赖网络), 到达后立即渲染本地插件;
        远程 fetch 在同一线程随后执行 (超时/失败不阻塞本地显示)
        """
        if self._fetching:
            return
        self._fetching = True
        self._show_loading()
        self._fetch_error = None
        self._start_polling()

        # 从配置读取远程 URL (主线程安全)
        repo_url = self.app.repo_url

        def _run():
            # 1. 本地扫描 (快, 无网络), 先行渲染
            try:
                installed = PluginRepo.scan_installed(self.app)
            except Exception as e:
                installed = {}
                self._fetch_error = f"本地扫描失败: {e}"
            self._result_queue.put({
                'type': 'local_done',
                'installed': installed,
            })

            # 2. 远程获取 (失败不影响已显示的本地列表)
            data = None
            try:
                data = PluginRepo.fetch_index(repo_url or None)
            except PluginRepoError as e:
                self._fetch_error = str(e)
            except Exception as e:
                self._fetch_error = f"未知错误: {e}"
            self._result_queue.put({'type': 'fetch_done', 'data': data})

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        # 强制刷新事件队列，确保 after 调度生效
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _on_local_done(self, installed):
        """主线程回调: 本地扫描完成 → 先渲染本地插件

        此时远程列表未知, 本地插件统一按"已安装"显示,
        不判定 orphan (等 fetch_done 后完整渲染再判定)
        """
        self._installed = installed
        self._render_list(local_only=True)

    def _on_fetch_done(self, data):
        """主线程回调: 远程 fetch 完成 → 合并远程 + 本地数据完整渲染

        远程获取失败时保留已显示的本地插件, 并在顶栏提示错误
        """
        self._fetching = False

        if data is not None:
            self._loaded = True
            self._remote_plugins = data.get('plugins', [])
            self._base_url = data.get('_base_url', '')
            self._last_refresh = time.time()
            self._update_time_label()
            self._fetch_error = None
        else:
            # 远程失败 → 清空远程数据, 保留本地
            self._remote_plugins = []
            self._base_url = ''
        self._update_error_banner()

        self._render_list()

    # ---- 渲染 ----

    def _update_error_banner(self):
        """顶栏错误提示: 远程获取失败时显示, 成功时隐藏"""
        if self._fetch_error:
            self._error_banner_lbl.config(
                text=f"⚠ {self._lbl['load_failed']}: {self._fetch_error}")
            self._error_banner.pack(fill=tk.X, side=tk.TOP)
        else:
            self._error_banner.pack_forget()

    def _show_loading(self):
        """显示加载中状态"""
        self._clear_canvas()
        s = self._s
        lbl = tk.Label(self._scrollable_frame, text=self._lbl['loading'],
                       bg=s['bg'], fg=s['hint'], font=(FONT_FAMILY, 11))
        lbl.pack(pady=40)

    def _render_list(self, local_only=False):
        """渲染插件卡片列表

        先构建合并列表 (每条包含 remote_info / local_info / status)
        再按复选框筛选渲染

        *local_only*: 远程列表尚未拿到时只渲染本地插件,
        此时不做 orphan 判定 (统一按"已安装"显示)
        """
        self._clear_canvas()
        s = self._s
        show_remote = self._show_remote_var.get()
        show_local = self._show_local_var.get()
        installed_map = self._installed

        # ---- 构建合并列表 ----
        merged = []          # [(display_pi, status, local_info, source)]
        seen = set()         # 已处理的 namespace

        if local_only:
            # 远程未知: 本地插件统一按"已安装"显示
            for ns, local_info in installed_map.items():
                pi = {
                    'name': ns,
                    'namespace': ns,
                    'version': local_info.get('version', ''),
                    'description': '',
                    'author': local_info.get('author', ''),
                }
                merged.append((pi, 'current', local_info, 'local'))
                seen.add(ns)
        else:
            # 远程插件
            for pi in self._remote_plugins:
                ns = pi.get('namespace', '')
                local_info = installed_map.get(ns)
                status = PluginRepo.compare_status(local_info, pi)
                merged.append((pi, status, local_info, 'remote'))
                seen.add(ns)

            # 本地 orphan (不在远程中的)
            for ns, local_info in installed_map.items():
                if ns not in seen:
                    pi = {
                        'name': ns,
                        'namespace': ns,
                        'version': local_info.get('version', ''),
                        'description': '',
                        'author': local_info.get('author', ''),
                    }
                    merged.append((pi, 'orphan', local_info, 'local'))
                    seen.add(ns)

        # ---- 按复选框筛选 ----
        total = 0
        for pi, status, local_info, source in merged:
            # 远程源: show_remote 不勾则跳过, 除非本地也有安装且 show_local 勾了
            if source == 'remote' and not show_remote:
                if not (local_info and show_local):
                    continue
            # 本地源: show_local 不勾则跳过
            if source == 'local' and not show_local:
                continue

            card = self._create_card(pi, status, local_info)
            self._cards.append((card, pi, status))
            card.pack(fill=tk.X, padx=10, pady=(4, 0))
            total += 1

        # 空状态
        if total == 0:
            lbl = tk.Label(self._scrollable_frame, text=self._lbl['no_plugins'],
                           bg=s['bg'], fg=s['hint'], font=(FONT_FAMILY, 11))
            lbl.pack(pady=40)
        else:
            tk.Frame(self._scrollable_frame, height=8, bg=s['bg']).pack()


    def _create_card(self, plugin_info, status, local_info):
        """创建单个插件卡片 Frame。"""
        s = self._s
        lbl = self._lbl
        card = tk.Frame(self._scrollable_frame, bg=s['card_bg'],
                        highlightthickness=1, highlightbackground=s['sep'],
                        padx=12, pady=10)

        # 第一行: 名称 + 版本 + 状态按钮
        row1 = tk.Frame(card, bg=s['card_bg'])
        row1.pack(fill=tk.X)

        name_text = plugin_info.get('name', plugin_info.get('namespace', '?'))
        name_lbl = tk.Label(row1, text=name_text, bg=s['card_bg'], fg=s['fg'],
                            font=(FONT_FAMILY, 11, 'bold'), anchor='w')
        name_lbl.pack(side=tk.LEFT)

        ver = plugin_info.get('version', '')
        if ver:
            ver_lbl = tk.Label(row1, text=f' v{ver}', bg=s['card_bg'],
                               fg=s['hint'], font=(FONT_FAMILY, 9))
            ver_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # 状态 / 操作按钮 (右侧)
        self._create_status_widget(row1, card, plugin_info, status, local_info)

        # 第二行: 作者 + 大小
        row2 = tk.Frame(card, bg=s['card_bg'])
        row2.pack(fill=tk.X, pady=(4, 0))

        author = plugin_info.get('author', '')
        size_kb = plugin_info.get('size_kb')

        meta_parts = []
        if author:
            meta_parts.append(author)
        if size_kb:
            meta_parts.append(lbl['size_kb'].format(size_kb))
        if meta_parts:
            meta_text = '  ·  '.join(meta_parts)
            meta_lbl = tk.Label(row2, text=meta_text, bg=s['card_bg'],
                                fg=s['hint'], font=(FONT_FAMILY, 8))
            meta_lbl.pack(side=tk.LEFT)

        # 第三行: 描述
        desc = plugin_info.get('description', '')
        if desc:
            # 截断过长的描述
            if len(desc) > 100:
                desc = desc[:97] + '...'
            desc_lbl = tk.Label(row2, text=desc, bg=s['card_bg'],
                                fg=s['fg'], font=(FONT_FAMILY, 9),
                                anchor='w', justify='left')
            desc_lbl.pack(side=tk.LEFT, padx=(20, 0))

        return card

    def _create_status_widget(self, row1, card, plugin_info, status, local_info):
        """在卡片右侧创建状态标签或操作按钮"""
        s = self._s
        lbl = self._lbl

        if status == 'install':
            btn = tk.Label(row1, text=lbl['install'],
                           bg=s['accent'], fg=s['accent_fg'],
                           font=(FONT_FAMILY, 9, 'bold'),
                           padx=14, pady=3, cursor='hand2',
                           relief=tk.FLAT)
            btn.pack(side=tk.RIGHT)
            btn.bind('<Button-1>',
                     lambda e, pi=plugin_info: self._on_install_click(pi))
            btn.bind('<Enter>',
                     lambda e, b=btn, c='#3a6fa8': b.config(bg=c))
            btn.bind('<Leave>',
                     lambda e, b=btn, c=s['accent']: b.config(bg=c))

        elif status == 'local':
            # 本地版本 + 远程存在 → 橙标 + 安装按钮 (提示覆盖)
            tag = tk.Label(row1, text=lbl['local_ver'],
                           bg=s['card_bg'], fg=s['warn'],
                           font=(FONT_FAMILY, 9),
                           padx=8, pady=3)
            tag.pack(side=tk.RIGHT, padx=(0, 4))
            btn = tk.Label(row1, text=lbl['install'],
                           bg=s['accent'], fg=s['accent_fg'],
                           font=(FONT_FAMILY, 9, 'bold'),
                           padx=14, pady=3, cursor='hand2',
                           relief=tk.FLAT)
            btn.pack(side=tk.RIGHT)
            btn.bind('<Button-1>',
                     lambda e, pi=plugin_info: self._on_overwrite_click(pi))
            btn.bind('<Enter>',
                     lambda e, b=btn, c='#3a6fa8': b.config(bg=c))
            btn.bind('<Leave>',
                     lambda e, b=btn, c=s['accent']: b.config(bg=c))
            # 删除按钮
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=False)

        elif status == 'update':
            installed_ver = local_info.get('version', '?') if local_info else '?'
            tag = tk.Label(row1, text=f"{lbl['current']} v{installed_ver}",
                           bg=s['card_bg'], fg=s['warn'],
                           font=(FONT_FAMILY, 9),
                           padx=8, pady=3)
            tag.pack(side=tk.RIGHT)

            new_ver = plugin_info.get('version', '')
            btn = tk.Label(row1, text=lbl['update_to'].format(new_ver),
                           bg=s['accent'], fg=s['accent_fg'],
                           font=(FONT_FAMILY, 9, 'bold'),
                           padx=10, pady=3, cursor='hand2',
                           relief=tk.FLAT)
            btn.pack(side=tk.RIGHT, padx=(4, 0))
            btn.bind('<Button-1>',
                     lambda e, pi=plugin_info, iv=installed_ver, rv=new_ver:
                     self._on_update_click(pi, iv, rv))
            btn.bind('<Enter>',
                     lambda e, b=btn, c='#3a6fa8': b.config(bg=c))
            btn.bind('<Leave>',
                     lambda e, b=btn, c=s['accent']: b.config(bg=c))
            # 删除按钮
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=False)

        elif status == 'orphan':
            tag = tk.Label(row1, text=lbl['orphan'],
                           bg=s['card_bg'], fg=s['hint'],
                           font=(FONT_FAMILY, 9),
                           padx=10, pady=3)
            tag.pack(side=tk.RIGHT)
            # 删除按钮 (孤儿插件, 无法恢复)
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=True)

        else:  # 'current'
            installed_ver = local_info.get('version', '') if local_info else ''
            tag = tk.Label(row1, text=f"{lbl['current']} v{installed_ver}",
                           bg=s['card_bg'], fg=s['success'],
                           font=(FONT_FAMILY, 9),
                           padx=10, pady=3)
            tag.pack(side=tk.RIGHT)
            # 删除按钮
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=False)

    # ---- 自定义对话框 (居中于插件窗口，替代系统 messagebox) ----

    def _confirm(self, title, message, ok_text=None):
        """自定义确认对话框，居中于插件窗口。返回 True/False。"""
        s = self._s
        lbl = self._lbl
        result = {'ok': False}

        dlg = tk.Toplevel(self)
        dlg.withdraw()  # 隐藏直到定位完成, 避免左上角闪烁
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.configure(bg=s['card_bg'])
        try:
            self.app.emit('app@window:set-icon', dlg)
        except Exception:
            pass

        body = tk.Frame(dlg, bg=s['card_bg'])
        body.pack(padx=24, pady=(20, 12))
        tk.Label(body, text='⚠', font=(FONT_FAMILY, 30), fg=s['warn'],
                 bg=s['card_bg']).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(body, text=message, font=(FONT_FAMILY, 10), fg=s['fg'],
                 bg=s['card_bg'], justify=tk.LEFT,
                 wraplength=320).pack(side=tk.LEFT, anchor='n')

        btn_frame = tk.Frame(dlg, bg=s['card_bg'])
        btn_frame.pack(pady=(0, 14))

        def _ok():
            result['ok'] = True
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        tk.Button(btn_frame, text=ok_text or lbl['ok'], command=_ok,
                  bg=s['accent'], fg=s['accent_fg'],
                  activebackground='#3a6fa8', activeforeground=s['accent_fg'],
                  font=(FONT_FAMILY, 10, 'bold'), padx=22, pady=4,
                  cursor='hand2', relief=tk.FLAT, bd=0,
                  highlightthickness=0).pack(side=tk.RIGHT)
        tk.Button(btn_frame, text=lbl['cancel'], command=_cancel,
                  bg=s['btn_bg'], fg=s['btn_fg'],
                  activebackground=s['hover'], activeforeground=s['btn_fg'],
                  font=(FONT_FAMILY, 10), padx=18, pady=4,
                  cursor='hand2', relief=tk.FLAT, bd=0,
                  highlightthickness=0).pack(side=tk.RIGHT, padx=(10, 0))
        dlg.protocol('WM_DELETE_WINDOW', _cancel)
        dlg.bind('<Escape>', lambda e: _cancel())

        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() - dw) // 2
        py = self.winfo_rooty() + (self.winfo_height() - dh) // 2
        dlg.geometry(f'{dw}x{dh}+{px}+{py}')
        dlg.deiconify()
        dlg.grab_set()
        dlg.focus_force()
        self.wait_window(dlg)
        return result['ok']

    def _notice(self, kind, title, message):
        """自定义提示对话框 (success/error/info), 居中于插件窗口"""
        s = self._s
        lbl = self._lbl
        icons = {'success': '✓', 'error': '✕', 'info': 'ℹ'}
        colors = {'success': s['success'], 'error': s['error'],
                  'info': s['accent']}

        dlg = tk.Toplevel(self)
        dlg.withdraw()
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.configure(bg=s['card_bg'])
        try:
            self.app.emit('app@window:set-icon', dlg)
        except Exception:
            pass

        body = tk.Frame(dlg, bg=s['card_bg'])
        body.pack(padx=24, pady=(20, 12))
        tk.Label(body, text=icons.get(kind, '•'),
                 font=(FONT_FAMILY, 28), fg=colors.get(kind, s['fg']),
                 bg=s['card_bg']).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(body, text=message, font=(FONT_FAMILY, 10), fg=s['fg'],
                 bg=s['card_bg'], justify=tk.LEFT,
                 wraplength=320).pack(side=tk.LEFT, anchor='n')

        btn_frame = tk.Frame(dlg, bg=s['card_bg'])
        btn_frame.pack(pady=(0, 14))
        tk.Button(btn_frame, text=lbl['ok'], command=dlg.destroy,
                  bg=s['accent'], fg=s['accent_fg'],
                  activebackground='#3a6fa8', activeforeground=s['accent_fg'],
                  font=(FONT_FAMILY, 10, 'bold'), padx=26, pady=4,
                  cursor='hand2', relief=tk.FLAT, bd=0,
                  highlightthickness=0).pack()
        dlg.bind('<Escape>', lambda e: dlg.destroy())
        dlg.protocol('WM_DELETE_WINDOW', dlg.destroy)

        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() - dw) // 2
        py = self.winfo_rooty() + (self.winfo_height() - dh) // 2
        dlg.geometry(f'{dw}x{dh}+{px}+{py}')
        dlg.deiconify()
        dlg.grab_set()
        dlg.focus_force()
        self.wait_window(dlg)

    # ---- 删除 ----

    def _add_delete_btn(self, row, plugin_info, local_info, is_orphan):
        """添加小型 [删除] 按钮"""
        s = self._s
        lbl = self._lbl
        namespace = plugin_info.get('namespace', '')
        pi_ref = dict(plugin_info) if plugin_info else {}
        li_ref = dict(local_info) if local_info else {}
        btn = tk.Label(row, text=lbl['delete'],
                       bg=s['card_bg'], fg=s['hint'],
                       font=(FONT_FAMILY, 8),
                       padx=6, pady=2, cursor='hand2',
                       relief=tk.FLAT)
        btn.pack(side=tk.RIGHT, padx=(8, 0))
        btn.bind('<Button-1>',
                 lambda e, ns=namespace, pi=pi_ref, li=li_ref, io=is_orphan:
                 self._on_delete_click(ns, pi, li, io))
        btn.bind('<Enter>',
                 lambda e, b=btn, c=s['error']: b.config(fg=c))
        btn.bind('<Leave>',
                 lambda e, b=btn, c=s['hint']: b.config(fg=c))

    def _on_delete_click(self, namespace, plugin_info, local_info, is_orphan):
        """删除确认对话框"""
        lbl = self._lbl
        name = plugin_info.get('name', namespace)
        ver = local_info.get('version', '') if local_info else ''

        if is_orphan:
            msg = lbl['delete_confirm_orphan'].format(name)
        else:
            msg = lbl['delete_confirm'].format(name, ver)

        if not self._confirm(lbl['confirm_title'], msg):
            return
        self._do_delete(namespace)

    def _do_delete(self, namespace):
        """执行删除: 移除插件目录, 刷新列表和菜单"""
        plugin_dir = os.path.join(self.app.plugin_path, namespace)
        try:
            if os.path.isdir(plugin_dir):
                shutil.rmtree(plugin_dir)
        except Exception as e:
            self._notice('error', self._lbl['delete'], f"删除失败: {e}")
            return

        # 立即从本地安装映射移除并刷新界面
        # 不能依赖 _fetch_plugin_list(): fetch 进行中会被 _fetching 跳过,
        # 且 fetch_done 会用旧映射重渲染导致删除"复活"
        self._installed.pop(namespace, None)
        if self._fetching:
            # fetch 未完成: 局部刷新本地列表, fetch_done 到达后会自动完整重渲染
            self._render_list(local_only=True)
        else:
            self._fetch_plugin_list()

    # ---- 覆盖安装 ----

    def _on_overwrite_click(self, plugin_info):
        """覆盖安装确认 (本地插件 + 远程存在)"""
        lbl = self._lbl
        name = plugin_info.get('name', '?')
        ver = plugin_info.get('version', '')

        if not self._confirm(lbl['confirm_title'],
                             lbl['confirm_overwrite'].format(name, ver)):
            return

        self._do_install(plugin_info)

    # ---- 筛选 ----

    def _on_filter_change(self):
        """复选框变化 — 最少一个勾选, 取消最后一个时自动切换到另一个"""
        if self._filter_changing:
            return
        self._filter_changing = True
        try:
            show_remote = self._show_remote_var.get()
            show_local = self._show_local_var.get()

            if not show_remote and not show_local:
                # 全不选 → 切到另一个（toggle 效果）
                if self._last_filter == 'local':
                    self._show_remote_var.set(True)
                    self._last_filter = 'remote'
                else:
                    self._show_local_var.set(True)
                    self._last_filter = 'local'
            else:
                if show_remote and not show_local:
                    self._last_filter = 'remote'
                elif show_local and not show_remote:
                    self._last_filter = 'local'
                else:
                    self._last_filter = 'both'

            self._render_list()
        finally:
            self._filter_changing = False

    def _clear_canvas(self):
        """清空画布和卡片列表"""
        for child in self._scrollable_frame.winfo_children():
            child.destroy()
        self._cards.clear()

    def _update_time_label(self):
        """更新底栏刷新时间"""
        if self._last_refresh:
            ts = time.strftime('%H:%M:%S', time.localtime(self._last_refresh))
            self._time_lbl.config(
                text=self._lbl['updated_at'].format(ts))
        else:
            self._time_lbl.config(text=self._lbl['never'])

    # ---- 操作 ----

    def _on_refresh(self):
        """点击刷新按钮"""
        self._fetch_plugin_list()

    def _on_install_click(self, plugin_info):
        """点击安装按钮 → 确认后开始下载"""
        name = plugin_info.get('name', '?')
        lbl = self._lbl

        if not self._confirm(lbl['confirm_title'],
                             lbl['confirm_install'].format(name)):
            return

        self._do_install(plugin_info)

    def _on_update_click(self, plugin_info, installed_ver, remote_ver):
        """点击更新按钮 → 确认后开始下载"""
        name = plugin_info.get('name', '?')
        lbl = self._lbl

        if not self._confirm(
                lbl['confirm_title'],
                lbl['confirm_update'].format(name, installed_ver, remote_ver)):
            return

        self._do_install(plugin_info)

    def _do_install(self, plugin_info):
        """启动后台安装线程"""
        install_dir = self.app.plugin_path
        namespace = plugin_info.get('namespace', '')
        url = plugin_info.get('url', '')
        version = plugin_info.get('version', '')
        name = plugin_info.get('name', namespace)
        author = plugin_info.get('author', '')
        base_url = self._base_url

        # 找到对应卡片并切换到进度显示
        self._set_card_progress(namespace)

        def _run():
            error = None
            try:
                PluginRepo.download_and_install(
                    url, base_url, install_dir, namespace,
                    version, author=author)
            except PluginRepoError as e:
                error = str(e)
            self._result_queue.put({
                'type': 'install_done',
                'namespace': namespace,
                'error': error,
            })

        self._install_thread = threading.Thread(target=_run, daemon=True)
        self._start_polling()
        self._install_thread.start()

    def _set_card_progress(self, namespace):
        """将指定 plugin 的卡片切换到进度显示"""
        if not self.winfo_exists():
            return
        for card, pi, status in self._cards:
            if pi.get('namespace') != namespace:
                continue
            s = self._s
            lbl = self._lbl
            for child in card.winfo_children():
                child.destroy()

            inner = tk.Frame(card, bg=s['card_bg'])
            inner.pack(fill=tk.X, padx=12, pady=10)
            name_text = pi.get('name', namespace)
            name_lbl = tk.Label(inner, text=name_text, bg=s['card_bg'],
                                fg=s['fg'], font=(FONT_FAMILY, 11, 'bold'))
            name_lbl.pack(side=tk.LEFT)

            progress_lbl = tk.Label(inner, text=lbl['downloading'].format(0),
                                    bg=s['card_bg'], fg=s['accent'],
                                    font=(FONT_FAMILY, 9))
            progress_lbl.pack(side=tk.RIGHT)
            setattr(card, '_progress_lbl', progress_lbl)
            break

    def _on_install_done(self, namespace, error=None):
        """安装完成回调 — 刷新列表和菜单"""
        if not self.winfo_exists():
            return
        if error:
            self._notice('error', self._lbl['install_failed'], error)
        else:
            self._notice('success', self._lbl['install_done'],
                         self._lbl['install_done'])

        # 重新扫描本地 + 重新 fetch 远程
        self._fetch_plugin_list()
