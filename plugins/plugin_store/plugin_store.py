# -*- coding: utf-8 -*-
"""Plugin Manager — browse, install & manage plugins."""
import os
import queue
import shutil
import threading
import time
import tkinter as tk

from plugins.plugin import GuiPlugin
from .repo import PluginRepo, PluginRepoError

#: 错误横幅配色（一次性危险面，成对使用，不走主题）
_ERR_BANNER_BG = '#5c2e2e'
_ERR_BANNER_FG = '#ffb4b4'

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
        'delete_title':  '确认删除',
        'delete_confirm': '确定要删除 "{}"{} 吗 ?\n\n可通过插件商店重新安装恢复。',
        'delete_confirm_orphan': '确定要删除 "{}" 吗 ?\n\n该插件是本地插件, 删除后无法通过插件商店恢复。',
        'delete_confirm_offline': '确定要删除 "{}" 吗 ?\n\n当前无法连接插件商店, 删除后无法重新安装。',
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
        'delete_title':  'Confirm',
        'delete_confirm': 'Delete "{}"{}?\n\nCan be reinstalled from the store.',
        'delete_confirm_orphan': 'Delete "{}"?\n\nThis is a local plugin and cannot be restored from the store.',
        'delete_confirm_offline': 'Delete "{}"?\n\nStore unreachable — cannot be reinstalled after deletion.',
        'delete_done':   'Deleted',
        'local_ver':     'Local Ver',
        'ok':            'OK',
        'cancel':        'Cancel',
    },
}


class PluginStore(GuiPlugin):
    """插件管理器 — 浏览、安装、管理本地及远程插件"""

    name = "Plugin Manager"
    name_zh = "插件管理器"
    name_en = "Plugin Manager"
    namespace = "plugin_store"
    priority = 998
    reload = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        lang_name = self.app.current_lang_name
        self._lbl = _LANG.get(lang_name, _LANG['en'])
        self._s = self.app.theme
        s = self._s

        self.title(self._lbl['title'])
        self.geometry("520x600")
        self.resizable(True, True)

        # ---- 状态 ----
        self._remote_plugins = []   # 远程插件列表
        self._installed = {}        # 本地已安装信息
        self._base_url = ''         # 远程配置 base URL
        self._fetch_error = None    # 最近一次 fetch 错误
        self._cards = []            # 当前渲染的卡片 (frame, info, status, source)
        self._empty_lbl = None      # 空状态 label (复用, 不反复创建)
        self._install_thread = None
        self._fetching = False      # 是否正在 fetch 中
        self._silent_fetch = False  # 静默刷新 (保留卡片, 完成后 diff)
        self._loaded = False        # 是否已成功加载过 (区分初始态与错误态)
        self._last_refresh = None
        self._result_queue = queue.Queue()  # 线程结果队列
        self._poll_id = None                # after ID for polling
        self._last_filter = 'both'          # 上次筛选状态: 'both'/'remote'/'local'
        self._filter_changing = False       # 防止 set() 触发递归
        self._destroyed = False             # 已销毁标记

        # ---- 远程/本地筛选复选框（位于底部 bar 右侧）----
        self._show_remote_var = tk.BooleanVar(value=True)
        self._show_local_var = tk.BooleanVar(value=True)

        # 错误提示条 (默认隐藏)
        self._error_banner = self.components.Frame(self, bg=_ERR_BANNER_BG)
        self._error_banner_lbl = self.components.Label(
            self._error_banner, text='', bg=_ERR_BANNER_BG, fg=_ERR_BANNER_FG,
            anchor=tk.W)
        self._error_banner_lbl.pack(fill=tk.X, padx=12, pady=3)

        # ---- 可滚动卡片列表区域 ----
        canvas_frame = self.components.Frame(self)
        # 右 8（滚动条距窗口边缘）+ 顶 8 底 4（与日志窗口一致）；
        # 左 0（内容边距由卡片 padx=8 提供）
        canvas_frame.pack(fill=tk.BOTH, expand=True, side=tk.TOP,
                          padx=(0, 8), pady=(8, 4))

        self._canvas = self.components.ScrollableCanvas(canvas_frame)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._scrollable_frame = self._canvas.inner

        # ---- 底栏（筛选 + 刷新靠右，时间靠左；高度自适应内容）----
        # bar 贴窗口边缘；bar 内按钮自带右 8 边距（与上方内容区右缘对齐）
        bottom = self.components.Frame(self, bg=s['bar'], height=32)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)

        self._time_lbl = self.components.Label(bottom, text=self._lbl['never'],
                                               bg=s['bar'], fg=s['hint'],
                                               font=self.components.font(8))
        self._time_lbl.pack(side=tk.LEFT, padx=10, pady=4)

        refresh_btn = self.components.Button(bottom,
                                             text=' ↻ ' + self._lbl['refresh'])
        refresh_btn.pack(side=tk.RIGHT, padx=(4, 8), pady=4)
        refresh_btn.bind('<Button-1>', lambda e: self._on_refresh())
        self._refresh_btn = refresh_btn

        cb_local = self.components.Checkbutton(
            bottom, text=self._lbl['filter_local'],
            variable=self._show_local_var,
            command=self._on_filter_change,
            bg=s['bar'], selectcolor=s['bar'])
        cb_local.pack(side=tk.RIGHT, padx=2, pady=4)
        cb_remote = self.components.Checkbutton(
            bottom, text=self._lbl['filter_remote'],
            variable=self._show_remote_var,
            command=self._on_filter_change,
            bg=s['bar'], selectcolor=s['bar'])
        cb_remote.pack(side=tk.RIGHT, padx=2, pady=4)

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

    def _fetch_plugin_list(self, silent=False):
        """在线程中获取远程插件列表和本地扫描

        本地扫描先行 (不依赖网络), 到达后立即渲染本地插件;
        远程 fetch 在同一线程随后执行 (超时/失败不阻塞本地显示)

        *silent*=True (刷新按钮): 保留现有卡片不清空, fetch 完成后 diff 更新;
        *silent*=False (首次加载): 显示 loading 并全量渲染.
        """
        if self._fetching:
            return
        self._fetching = True
        self._silent_fetch = silent
        if not silent:
            self._show_loading()
        self._fetch_error = None
        # 禁用刷新按钮: 背景置灰 (主题 disabled_bg)
        self._refresh_btn.config(state=tk.DISABLED,
                                 bg=self._s['Button']['disabled_bg'])
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

            # 2. 远程获取 (失败不影响已显示的本地列表);
            #    传入软件版本, 由 fetch_index 过滤类型/版本不兼容的插件
            data = None
            try:
                data = PluginRepo.fetch_index(repo_url or None,
                                              app_type=self.app.app_type,
                                              app_version=self.app.app_version)
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
        if not self._silent_fetch:
            self._render_list(local_only=True)

    def _on_fetch_done(self, data):
        """主线程回调: 远程 fetch 完成 → 合并远程 + 本地数据完整渲染

        远程获取失败时保留已显示的本地插件, 并在顶栏提示错误
        """
        self._fetching = False
        self._silent_fetch = False
        self._refresh_btn.config(state=tk.NORMAL,
                                 bg=self._s['Button']['bg'])

        if data is not None:
            self._loaded = True
            self._remote_plugins = data.get('plugins', [])
            self._base_url = data.get('_base_url', '')
            self._last_refresh = time.time()
            self._update_time_label()
            self._fetch_error = None
            self._update_error_banner()
            # diff 渲染: 只更新变化的卡片 (数据未变则零重建)
            self._sync_plugins(None)
        else:
            # 远程失败: 旧远程数据不可信, 移除远程卡片,
            # 只保留本地插件 (local_only 简化显示), 并提示错误
            self._remote_plugins = []
            self._base_url = ''
            self._update_error_banner()
            self._prune_to_local_only()

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
        """显示加载中状态（顶部对齐，避免加载时上边距看起来偏大）"""
        self._clear_canvas()
        s = self._s
        lbl = self.components.Label(self._scrollable_frame,
                                    text=self._lbl['loading'],
                                    fg=s['hint'], font=self.components.font(11))
        lbl.pack(anchor='n', pady=20)

    def _render_list(self, local_only=False):
        """渲染插件卡片列表 — 始终创建全部卡片 (不过滤).

        筛选显隐由 _apply_filter 统一控制 (卡片复用, 不销毁重建);
        后续数据变化走 _sync_plugins 卡片级 diff.

        *local_only*: 远程列表尚未拿到时只渲染本地插件,
        此时不判定状态 (统一按 'local_only' 显示, 仅删除按钮)
        """
        self._clear_canvas()
        installed_map = self._installed

        # ---- 构建合并列表 ----
        merged = []          # [(display_pi, status, local_info, source)]
        seen = set()         # 已处理的 namespace

        if local_only:
            # 远程未知: 本地插件只显示删除按钮 (fetch 成功后 diff 更新)
            for ns, local_info in installed_map.items():
                pi = {
                    'name': ns,
                    'namespace': ns,
                    'version': local_info.get('version', ''),
                    'description': local_info.get('description', ''),
                    'author': local_info.get('author', ''),
                }
                merged.append((pi, 'local_only', local_info, 'local'))
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
                        'description': local_info.get('description', ''),
                        'author': local_info.get('author', ''),
                    }
                    merged.append((pi, 'orphan', local_info, 'local'))
                    seen.add(ns)

        # 排序规则: 全部按 namespace 排序 (稳定, 与 _reorder_cards 一致)
        merged.sort(key=lambda m: m[0].get('namespace', ''))

        # 创建全部卡片 (筛选由 _apply_filter 控制显隐)
        for pi, status, local_info, source in merged:
            card = self._create_card(pi, status, local_info)
            self._cards.append((card, pi, status, source))
            card.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._apply_filter()

    def _apply_filter(self):
        """筛选变化: 复用已有卡片, 只 pack/pack_forget, 不销毁重建.

        与旧 _render_list 的可见性规则一致:
        远程源 → show_remote 或 (已安装 且 show_local);
        本地源 (orphan) → show_local.

        先全部 forget 再按 namespace 排序 pack — 直接 pack() 会把
        重新显示的卡片放到布局末尾, 导致切换筛选后顺序错乱.
        """
        show_remote = self._show_remote_var.get()
        show_local = self._show_local_var.get()
        installed = self._installed
        for card, pi, _status, _source in self._cards:
            card.pack_forget()
        visible = 0
        for card, pi, _status, source in sorted(
                self._cards, key=lambda x: x[1].get('namespace', '')):
            ns = pi.get('namespace', '')
            if source == 'remote':
                show = show_remote or (ns in installed and show_local)
            else:
                show = show_local
            if show:
                card.pack(fill=tk.X, padx=8, pady=(0, 4))
                visible += 1

        self._update_empty_state()

    def _update_empty_state(self):
        """空状态 label 显隐 (复用, 不反复创建) — 供筛选与单卡同步共用.

        用 winfo_manager() 判断 pack 状态 (pack 后立即返回 'pack'),
        不用 winfo_ismapped() — 布局完成前 ismapped 仍为 False,
        会把刚 pack 的卡片误判为不可见.
        """
        visible = sum(1 for c, _pi, _st, _src in self._cards
                      if c.winfo_manager() == 'pack')
        if visible == 0:
            if self._empty_lbl is None:
                self._empty_lbl = self.components.Label(
                    self._scrollable_frame, text=self._lbl['no_plugins'],
                    fg=self._s['hint'], font=self.components.font(11))
            self._empty_lbl.pack(pady=40)
        elif self._empty_lbl is not None:
            self._empty_lbl.pack_forget()

    # ---- 卡片级 diff 同步 (删除/安装/刷新后按需更新, 不 fetch 远程) ----

    def _sync_plugins(self, namespaces=None):
        """同步卡片与当前数据一致 — 只重建变化的卡片.

        *namespaces*=None: 同步全部 (远程 + 本地 orphan), 并移除已消失的卡片
        (刷新/远程 fetch 完成后用); *namespaces*=[ns,...]: 只同步指定插件
        (删除/安装后用). 不调用 _fetch_plugin_list(), 无网络请求.
        """
        installed = PluginRepo.scan_installed(self.app)
        self._installed = installed

        if namespaces is None:
            ns_set = {p.get('namespace', '') for p in self._remote_plugins}
            ns_set.update(installed.keys())
            # 移除已消失的卡片 (远程删除且本地无)
            for card, pi, _st, _src in list(self._cards):
                if pi.get('namespace', '') not in ns_set:
                    card.destroy()
                    self._cards.remove((card, pi, _st, _src))
        else:
            ns_set = set(namespaces)

        for ns in ns_set:
            self._sync_one_card(ns, installed)
        if namespaces is None:
            # 全量同步后校正卡片顺序 (local_only 渲染顺序可能 ≠ 远程顺序)
            self._reorder_cards()
            self._apply_filter()
        else:
            # 单卡同步 (删除/安装): 不重排全部卡片 (避免整个列表刷新),
            # 只更新空状态
            self._update_empty_state()

    def _reorder_cards(self):
        """按 namespace 排序重排卡片 pack 顺序 (稳定, 与渲染规则一致).

        只移动 pack 位置, 不销毁任何卡片.
        """
        order = sorted({pi.get('namespace', '') for _c, pi, _st, _src
                        in self._cards})

        prev = None
        for ns in order:
            card = next((c for c, pi, _st, _src in self._cards
                         if pi.get('namespace') == ns), None)
            if card is None:
                continue
            if prev is not None:
                card.pack(after=prev, fill=tk.X, padx=8, pady=(0, 4))
            else:
                card.pack(fill=tk.X, padx=8, pady=(0, 4))
            prev = card

    def _sync_one_card(self, ns, installed):
        """同步单个插件卡片: 缺失则插入, 状态/数据变化则重建, 无变化不动."""
        local = installed.get(ns)
        pi = next((p for p in self._remote_plugins
                   if p.get('namespace') == ns), None)
        if pi is None:
            if local is None:
                # 远程与本地都不存在 (如 orphan 删除) → 移除现有卡片
                for i, (c, p, _st, _src) in enumerate(self._cards):
                    if p.get('namespace') == ns:
                        c.destroy()
                        self._cards.pop(i)
                        break
                return
            pi = {
                'name': ns,
                'namespace': ns,
                'version': local.get('version', ''),
                'description': local.get('description', ''),
                'author': local.get('author', ''),
            }
            source, status = 'local', 'orphan'
        else:
            source = 'remote'
            status = PluginRepo.compare_status(local, pi)

        idx = None
        for i, (c, p, st, src) in enumerate(self._cards):
            if p.get('namespace') == ns:
                idx = i
                break

        if idx is None:
            self._insert_card(pi, status, local, source)
            return
        old = self._cards[idx]
        if (old[2] != status
                or (old[1].get('name'), old[1].get('version'))
                != (pi.get('name'), pi.get('version'))):
            self._replace_card(idx, pi, status, local, source)
        # 无变化 → 不动

    def _prune_to_local_only(self):
        """远程失败: 移除未安装的远程卡片, 所有本地已安装插件降级
        local_only 显示 (仅删除按钮).

        旧远程数据不可信 (获取失败), 只保留本地插件; 本地已安装插件的
        卡片 source 可能是 'remote' (远程列表含它), 不能移除.
        下次 fetch 成功后由 _sync_plugins 恢复完整状态.
        """
        installed = self._installed
        for card, pi, st, src in list(self._cards):
            ns = pi.get('namespace', '')
            if src == 'remote' and ns not in installed:
                # 未安装的远程插件: 移除
                card.destroy()
                self._cards.remove((card, pi, st, src))
            elif st != 'local_only':
                idx = self._cards.index((card, pi, st, src))
                self._replace_card(idx, pi, 'local_only',
                                   installed.get(ns), 'local')
        self._apply_filter()

    def _insert_card(self, pi, status, local, source):
        """按 namespace 排序插入新卡片 (插到排序后其下一个 ns 的卡片之前)."""
        before = None
        ns = pi.get('namespace', '')
        all_ns = sorted({pp.get('namespace', '') for _c, pp, _st, _src
                         in self._cards} | {ns})
        pos = all_ns.index(ns)
        if pos + 1 < len(all_ns):
            nxt = all_ns[pos + 1]
            before = next((c for c, pp, _st, _src in self._cards
                           if pp.get('namespace') == nxt), None)
        card = self._create_card(pi, status, local)
        if before is not None:
            card.pack(before=before, fill=tk.X, padx=8, pady=(0, 4))
        else:
            card.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._cards.append((card, pi, status, source))

    def _replace_card(self, idx, pi, status, local, source):
        """销毁并重建第 idx 张卡片, 保持其在 _scrollable_frame 中的位置.

        winfo_children 是创建顺序而非布局顺序 (卡片经插入/重排后两者
        不一致), 须按布局 winfo_y 排序后找紧邻的下一个兄弟.
        """
        old = self._cards[idx][0]
        old_y = old.winfo_y()
        after = None
        siblings = [(w.winfo_y(), w) for w in self._scrollable_frame.winfo_children()
                    if w is not old and w is not self._empty_lbl
                    and w.winfo_ismapped()]
        for y, w in sorted(siblings):
            if y > old_y:
                after = w
                break
        old.destroy()
        card = self._create_card(pi, status, local)
        if after is not None:
            card.pack(before=after, fill=tk.X, padx=8, pady=(0, 4))
        else:
            card.pack(fill=tk.X, padx=8, pady=(0, 4))
        self._cards[idx] = (card, pi, status, source)

    def _create_card(self, plugin_info, status, local_info):
        """创建单个插件卡片 Frame。"""
        s = self._s
        lbl = self._lbl
        card = self.components.Card(self._scrollable_frame, padx=12, pady=10)

        # 第一行: 名称 + 版本 + 状态按钮
        row1 = self.components.Frame(card, bg=s['card'])
        row1.pack(fill=tk.X)

        name_text = plugin_info.get('name', plugin_info.get('namespace', '?'))
        name_lbl = self.components.Label(row1, text=name_text, bg=s['card'],
                                         font=self.components.font(11, 'bold'),
                                         anchor='w')
        name_lbl.pack(side=tk.LEFT)

        ver = plugin_info.get('version') or ''
        if ver:
            ver_lbl = self.components.Label(row1, text=f' v{ver}', bg=s['card'],
                                            fg=s['hint'])
            ver_lbl.pack(side=tk.LEFT, padx=(4, 0))

        # 状态 / 操作按钮 (右侧)
        self._create_status_widget(row1, card, plugin_info, status, local_info)

        # 第二行: 作者 + 大小
        row2 = self.components.Frame(card, bg=s['card'])
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
            meta_lbl = self.components.Label(row2, text=meta_text, bg=s['card'],
                                             fg=s['hint'], font=self.components.font(8))
            meta_lbl.pack(side=tk.LEFT)

        # 第三行: 描述
        desc = plugin_info.get('description', '')
        if desc:
            # 截断过长的描述
            if len(desc) > 100:
                desc = desc[:97] + '...'
            desc_lbl = self.components.Label(row2, text=desc, bg=s['card'],
                                             anchor='w', justify='left')
            desc_lbl.pack(side=tk.LEFT, padx=(20, 0))

        return card

    def _create_status_widget(self, row1, card, plugin_info, status, local_info):
        """在卡片右侧创建状态标签或操作按钮"""
        s = self._s
        lbl = self._lbl

        if status == 'local_only':
            # 远程数据不可用: 不显示状态标签, 只保留删除按钮
            # (fetch 成功后由 _sync_plugins 更新为真实状态)
            # is_orphan='offline': 删除确认用"无法连接商店"文案
            self._add_delete_btn(row1, plugin_info, local_info,
                                 is_orphan='offline')
            return

        if status == 'install':
            btn = self.components.Button(
                row1, text=lbl['install'],
                font=self.components.font(9, 'bold'),
                padx=12, pady=1)
            btn.pack(side=tk.RIGHT)
            btn.bind('<Button-1>',
                     lambda e, pi=plugin_info: self._on_install_click(pi))

        elif status == 'local':
            # 本地版本 + 远程存在 → 橙标 + 安装按钮 (提示覆盖)
            btn = self.components.Button(
                            row1, text=lbl['install'],
                            font=self.components.font(9, 'bold'),
                            padx=12, pady=1)
            btn.pack(side=tk.RIGHT)
            tag = self.components.Label(row1, text=lbl['local_ver'],
                                        bg=s['card'], fg=s['warn'])
            tag.pack(side=tk.RIGHT)
            
            btn.bind('<Button-1>', lambda e, pi=plugin_info: self._on_overwrite_click(pi))
            # 删除按钮
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=False)

        elif status == 'update':
            # 本地无版本 → 不显示版本号 (无裸 v)
            installed_ver = (local_info.get('version') or '') if local_info else ''
            ver_text = f" v{installed_ver}" if installed_ver else ''
            tag = self.components.Label(row1, text=f"{lbl['current']}{ver_text}",
                                        bg=s['card'], fg=s['warn'])
            tag.pack(side=tk.RIGHT)

            new_ver = plugin_info.get('version', '')
            btn = self.components.Button(
                row1, text=lbl['update_to'].format(new_ver),
                bg=s['accent'], fg=s['accent_fg'],
                font=self.components.font(9, 'bold'))
            btn.pack(side=tk.RIGHT, padx=(4, 0))
            btn.bind('<Button-1>',
                     lambda e, pi=plugin_info, iv=installed_ver, rv=new_ver:
                     self._on_update_click(pi, iv, rv))
            # 删除按钮
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=False)

        elif status == 'orphan':
            tag = self.components.Label(row1, text=lbl['orphan'],
                                        bg=s['card'], fg=s['hint'])
            tag.pack(side=tk.RIGHT)
            # 删除按钮 (孤儿插件, 无法恢复)
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=True)

        else:  # 'current'
            # 本地无版本 → 不显示版本号 (无裸 v)
            installed_ver = (local_info.get('version') or '') if local_info else ''
            ver_text = f" v{installed_ver}" if installed_ver else ''
            tag = self.components.Label(row1, text=f"{lbl['current']}{ver_text}",
                                        bg=s['card'], fg=s['success'])
            tag.pack(side=tk.RIGHT)
            # 删除按钮
            self._add_delete_btn(row1, plugin_info, local_info, is_orphan=False)

    # ---- 删除 ----

    def _add_delete_btn(self, row, plugin_info, local_info, is_orphan):
        """添加小型 [删除] 按钮"""
        s = self._s
        lbl = self._lbl
        namespace = plugin_info.get('namespace', '')
        pi_ref = dict(plugin_info) if plugin_info else {}
        li_ref = dict(local_info) if local_info else {}
        btn = self.components.Button(
            row, text=lbl['delete'], bg=s['card'], fg=s['hint'],
            font=self.components.font(8), padx=6, pady=2)
        btn.pack(side=tk.RIGHT, padx=(8, 0))
        btn.bind('<Button-1>',
                 lambda e, ns=namespace, pi=pi_ref, li=li_ref, io=is_orphan:
                 self._on_delete_click(ns, pi, li, io))
        # 同时设 activeforeground: 点击确认弹窗(模态 grab)后按钮可能
        # stuck 在 active 状态, 此时仅 fg 不生效, 需同步 activeforeground
        btn.bind('<Enter>', lambda e, b=btn, c=s['danger']: b.config(fg=c, activeforeground=c))
        btn.bind('<Leave>', lambda e, b=btn, c=s['hint']: b.config(fg=c, activeforeground=c))

    def _on_delete_click(self, namespace, plugin_info, local_info, is_orphan):
        """删除确认对话框"""
        lbl = self._lbl
        name = plugin_info.get('name', namespace)
        ver = (local_info.get('version') or '') if local_info else ''

        if is_orphan == 'offline':
            # 远程不可用 (local_only): 删除后无法重新安装
            msg = lbl['delete_confirm_offline'].format(name)
        elif is_orphan:
            msg = lbl['delete_confirm_orphan'].format(name)
        else:
            # 无版本 → 不拼 " v" 段 (避免 vNone / 裸 v)
            msg = lbl['delete_confirm'].format(
                name, f' v{ver}' if ver else '')

        if not self.components.askyesno(self, lbl['delete_title'], msg):
            return
        self._do_delete(namespace)

    def _do_delete(self, namespace):
        """执行删除: 移除插件目录, 刷新列表和菜单"""
        plugin_dir = os.path.join(self.app.plugin_path, namespace)
        try:
            if os.path.isdir(plugin_dir):
                shutil.rmtree(plugin_dir)
        except Exception as e:
            self.components.showerror(self, self._lbl['delete'], f"删除失败: {e}")
            return

        # 按需更新: 只同步该插件卡片 (移除/变回可安装), 不 fetch 远程.
        # _sync_plugins 内部重扫本地, fetch 进行中也安全 (fetch_done 后全量兜底)
        self._sync_plugins([namespace])

    # ---- 覆盖安装 ----

    def _on_overwrite_click(self, plugin_info):
        """覆盖安装确认 (本地插件 + 远程存在)"""
        lbl = self._lbl
        name = plugin_info.get('name', '?')
        ver = plugin_info.get('version', '')

        if not self.components.askyesno(self, lbl['confirm_title'],
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

            self._apply_filter()
        finally:
            self._filter_changing = False

    def _clear_canvas(self):
        """清空画布和卡片列表"""
        for child in self._scrollable_frame.winfo_children():
            child.destroy()
        self._cards.clear()
        self._empty_lbl = None

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
        """点击刷新按钮 — 静默刷新 (保留卡片, 完成后 diff 更新)"""
        self._fetch_plugin_list(silent=True)

    def _on_install_click(self, plugin_info):
        """点击安装按钮 → 确认后开始下载"""
        name = plugin_info.get('name', '?')
        lbl = self._lbl

        if not self.components.askyesno(self, lbl['confirm_title'],
                                        lbl['confirm_install'].format(name)):
            return

        self._do_install(plugin_info)

    def _on_update_click(self, plugin_info, installed_ver, remote_ver):
        """点击更新按钮 → 确认后开始下载"""
        name = plugin_info.get('name', '?')
        lbl = self._lbl

        if not self.components.askyesno(
                self, lbl['confirm_title'],
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
        for card, pi, _status, _source in self._cards:
            if pi.get('namespace') != namespace:
                continue
            s = self._s
            lbl = self._lbl
            for child in card.winfo_children():
                child.destroy()

            inner = self.components.Frame(card, bg=s['card'])
            inner.pack(fill=tk.X, padx=12, pady=10)
            name_text = pi.get('name', namespace)
            name_lbl = self.components.Label(inner, text=name_text, bg=s['card'],
                                             font=self.components.font(11, 'bold'))
            name_lbl.pack(side=tk.LEFT)

            progress_lbl = self.components.Label(
                inner, text=lbl['downloading'].format(0),
                bg=s['card'], fg=s['accent'])
            progress_lbl.pack(side=tk.RIGHT)
            setattr(card, '_progress_lbl', progress_lbl)
            break

    def _on_install_done(self, namespace, error=None):
        """安装完成回调 — 刷新列表和菜单"""
        if not self.winfo_exists():
            return
        # 按需更新该插件卡片 (成功变"已安装", 失败恢复原状态), 不 fetch 远程
        self._sync_plugins([namespace])
        if error:
            self.components.showerror(self, self._lbl['install_failed'], error)
        # 成功: 卡片进度 → "已安装"状态即反馈, 不弹窗
