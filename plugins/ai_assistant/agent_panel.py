# -*- coding: utf-8 -*-
"""AgentPanel — Agent 交互面板 (聊天 UI), 纯前端消费 agent 服务.

与服务通信: services.call('agent@ask', ...) 发起, 订阅 agent@* 事件
渲染流式输出。AgentService 由 manager 内置启动 (BUILTIN_SERVICES),
面板不负责服务的生命周期。
"""
import json
import os
import time
import copy
import tkinter as tk

from plugins.plugin import GuiPlugin

from .config import load_json, CONFIG_DIR, Config
from .core.llm import list_detected_proxies
from .settings_window import AgentSettingsWindow

_HIST_PATH = os.path.join(CONFIG_DIR, 'agent_input_history.json')
_HIST_MAX = 50   # 输入历史上限


_SOURCE_ZH = {'env': '环境变量', 'claude': 'Claude 配置',
              'codex': 'Codex 配置', 'config': '配置文件'}
_SOURCE_EN = {'env': 'environment', 'claude': 'Claude config',
              'codex': 'Codex config', 'config': 'config file'}

LANG = {
    'zh': {
        'title': '小U',
        'send': '发送', 'stop': '停止',
        'clear_chat': '清空会话',
        'base_url': '端点', 'model': '模型',
        'settings': '配置',
        'err_empty': '输入为空',
        'err_no_service': '小U 服务不可用',
        'err_no_api_key': '没有配置该端点的API KEY, 请先到配置窗口配置或者更换可用的端点',
        'you': '你', 'agent': '小U',
        'tool': '工具', 'tool_result': '结果',
        'key_found': '已自动匹配 API KEY (来源: %s)',
        'key_not_found': '未找到匹配的 API KEY, 请到配置窗口填写',
        'carry_ctx': '保存上下文 (多轮对话)',
        'enter_send': '回车发送',
        'local_first': '本地优先',
        'local_first_help': '优先使用本地匹配, 本地匹配不依赖大模型, 匹配不上才使用大模型',
        'local_not_first_help': '禁止本地匹配, 直接使用大模型',
        'stopped': '已停止',
        'thinking': '思考中…',
        'waiting_round': '等待模型响应 (第%d轮)…',
        'running_tool': '正在执行工具: %s…',
        'time_round': '第%d轮 %.1fs',
        'time_ttft': ' (TTFT %.1fs)',
        'time_ttft_lone': 'TTFT %.1fs',
        'time_tool': '⚙ %s %.1fs',
        'time_total': '⏱ 总 %.1fs',
        'proxy': '代理',
        'proxy_none': '无',
        'busy_hint': '上一条还在生成中… (可点击"停止"中断)',
        'single_turn': '（单轮，未保存上下文）',
        'welcome': ('💡 我是小U, 可以帮你:\n'
                    '• 打开插件 —— 如「打开任务调度器」「启动插件审查器」\n'
                    '• 启动外部工具 —— 如「打开设备管理器」「启动终端」\n'
                    '• 定时任务 —— 如「10分钟后提醒我喝水」'
                    '「每天9点提醒我打卡」\n'
                    '• 系统通知 —— 如「弹个窗告诉我该下班了」\n'
                    '也可以直接聊天提问; 点击工具调用行可展开完整结果。'),
        'confirm_clear': '确定清空会话历史？此操作不可恢复',
        'tokens': 'tokens: 共 %s, 输入 %s, 输出 %s',
        'cache_detail': ' (命中 %s, 占比 %d%%)',
        'stat_hit_fmt': ' (%s %s, 占比 %d%%)',
        'stat_total': '累计',
        'stat_in': '入',
        'stat_out': '出',
        'stat_hit': '缓存',
    },
    'en': {
        'title': 'U-Bot',
        'send': 'Send', 'stop': 'Stop',
        'clear_chat': 'Clear chat',
        'base_url': 'Base', 'model': 'Model',
        'settings': 'Configuration',
        'err_empty': 'Input is empty',
        'err_no_service': 'U-Bot service not running',
        'err_no_api_key': 'The API KEY for this endpoint is not configured. Please configure it in the configuration window or change to a usable endpoint.',
        'you': 'You', 'agent': 'U-Bot',
        'tool': 'Tool', 'tool_result': 'Result',
        'key_found': 'API KEY auto-filled (source: %s)',
        'key_not_found': 'No matching API KEY found, fill it in Configuration',
        'carry_ctx': 'Save context (multi-turn)',
        'enter_send': 'Enter to send',
        'local_first': 'Local first',
        'local_first_help': 'Prioritize local matching. Local matching does not depend on the large model; the large model is only used if a match cannot be found',
        'local_not_first_help': 'Disable local matching and use the large model directly',
        'stopped': 'Stopped',
        'thinking': 'Thinking…',
        'waiting_round': 'Waiting for model (round %d)…',
        'running_tool': 'Running tool: %s…',
        'time_round': 'round %d %.1fs',
        'time_ttft': ' (TTFT %.1fs)',
        'time_ttft_lone': 'TTFT %.1fs',
        'time_tool': '⚙ %s %.1fs',
        'time_total': '⏱ total %.1fs',
        'proxy': 'Proxy',
        'proxy_none': 'None',
        'busy_hint': 'Still generating… (click Stop to interrupt)',
        'single_turn': '(single-turn, not saved to context)',
        'welcome': ('💡 I\'m U-Bot. I can:\n'
                    '• Open plugins — e.g. "open Task Scheduler"\n'
                    '• Launch external tools — e.g. "open Device Manager"\n'
                    '• Schedule tasks — e.g. "remind me to stretch '
                    'in 10 minutes"\n'
                    '• Send notifications — e.g. "pop up a reminder"\n'
                    'Or just chat. Click a tool-call row to expand '
                    'its full result.'),
        'confirm_clear': 'Clear conversation history? This cannot be undone',
        'tokens': 'tokens: total %s, in %s, out %s',
        'cache_detail': ' (hit %s, %d%%)',
        'stat_hit_fmt': ' (%s %s, %d%%)',
        'stat_total': 'Total',
        'stat_in': 'in',
        'stat_out': 'out',
        'stat_hit': 'hit',
    },
}


class AgentPanel(GuiPlugin):
    """Agent chat panel — 前端, 业务全在 AgentService."""

    name = "小U"
    name_zh = "小U"
    name_en = "U-Bot"
    namespace = "agent_panel"
    priority = 1000
    reload = True
    fixed_position = False
    fixed_size = False

    def __init__(self, parent=None, app=None):
        super().__init__(parent, app)
        lang = self.app.current_lang_name
        self._l = LANG.get(lang, LANG['en'])
        self.theme = self.app.theme

        self.title(self._l['title'])
        self.resizable(True, True)
        self.configure(bg=self.theme['bar'])

        self._task_id = None        # 当前任务 (同一时间只跟一个)
        self._pending = []          # chunk 攒批
        self._timings = []          # 耗时事件缓冲 (done 时合成一行时间线)
        self._after_job = None
        self._t_send = None         # 本次提问起点 (总耗时统计)
        self._total_tokens = 0      # 面板存续期累计 token 消耗
        self._total_hit = 0         # 其中缓存命中 (端点不报则恒 0, 不显示)
        self._total_prompt = 0      # 累计输入
        self._total_completion = 0  # 累计输出
        self._settings_win = None   # 设置窗口单实例引用
        self._tool_rows = []        # 工具折叠行状态 (点击展开/收起完整结果)
        # 输入历史 (持久化, 上下箭头回填)
        hist = load_json(_HIST_PATH, [])
        self._hist = hist if isinstance(hist, list) else []
        self._hist_idx = -1         # -1 = 未进入历史浏览
        self._hist_draft = ''       # 进入历史浏览前的未发送草稿

        self._config = getattr(self.app, 'agent_config', None)
        if not self._config:
            self._config = Config()
        # 看实际情况需不需要reload, 这里reload主要是为了加载最新的配置(可能手工修改了配置文件或者从claude/codex配置中匹配api_key)
        self._config.reload()

        # 服务事件订阅 (框架在插件销毁时自动清理)
        self.app.on('agent@chunk', self._on_chunk)
        self.app.on('agent@local', self._on_local)
        self.app.on('agent@progress', self._on_progress)
        self.app.on('agent@timing', self._on_timing)
        self.app.on('agent@tool_call', self._on_tool_call)
        self.app.on('agent@tool_result', self._on_tool_result)
        self.app.on('agent@done', self._on_done)
        self.app.on('agent@error', self._on_error)
        # # 主题切换时刷新 markdown tag 颜色
        # self.app.on('app@theme:changed', self._on_theme_changed)

        self._build_ui()
        self.app.emit('app@window:set-geometry', self, w=750, h=580)
        self._restore_session()
        self._on_local_first_check()
        self._txt_chat.see(tk.END)
        self._update_combobox(self._config.providers)

    # ---- UI ----

    def _make_scrollable_text(self, parent, **kwargs):
        kwargs.setdefault('font', self.components.mono_font(10))
        kwargs.setdefault('height', 1)
        kwargs.setdefault('wrap', tk.WORD)
        return self.components.ScrollableText(parent, **kwargs)

    @staticmethod
    def _get_text(widget):
        return widget.get('1.0', 'end-1c')

    @staticmethod
    def _set_editable_text(widget, text):
        widget.delete('1.0', tk.END)
        widget.insert('1.0', text)

    # ---- 输入历史 (上下箭头回填) ----

    def _on_input_hist(self, event):
        """输入区 Up/Down: 光标在首/末行时历史回填, 否则正常光标移动."""
        w = self._txt_input
        line = int(w.index('insert').split('.')[0])
        total = int(w.index('end-1c').split('.')[0])
        if event.keysym == 'Up' and line == 1:
            self._hist_step(-1)
            return 'break'
        if event.keysym == 'Down' and line == total:
            self._hist_step(1)
            return 'break'
        return None

    def _hist_step(self, delta):
        """历史浏览: -1 回更早一条, +1 回更新一条/恢复草稿退出."""
        if not self._hist:
            return
        if self._hist_idx == -1:
            # 首次进入: 暂存未发送草稿, 游标置于末条之后
            self._hist_draft = self._get_text(self._txt_input)
            self._hist_idx = len(self._hist)
        self._hist_idx += delta
        if self._hist_idx < 0:
            self._hist_idx = 0
        elif self._hist_idx >= len(self._hist):
            # 超出末条: 恢复草稿并退出历史浏览
            self._set_editable_text(self._txt_input, self._hist_draft)
            self._hist_idx = -1
            return
        self._set_editable_text(self._txt_input,
                                self._hist[self._hist_idx])

    def _on_input_edit(self, event):
        """实际编辑 (非历史导航键) 时退出历史浏览态."""
        if event.keysym in ('Up', 'Down'):
            return None
        self._hist_idx = -1
        return None

    def _on_input_return(self, _event):
        """回车: 勾选"回车发送"时直接发送, 否则正常换行 (Shift+Enter 始终换行)."""
        if self._enter_send.get():
            if not self._get_text(self._txt_input).strip():
                return 'break'
            self._try_send()
            return 'break'
        return None

    def _try_send(self):
        """回车路径发送 — 任务进行中不抢停 (停止只走按钮点击), 提示且保留输入."""
        if self._task_id is not None:
            self._append_chat('[%s]\n' % self._l['busy_hint'], 'ai_meta')
            return
        self._send()

    def _set_thinking(self, on):
        """状态行: 发送后/工具返回后的静默期显示"思考中…", 首个 chunk 或终态清除."""
        self._lbl_status.config(text=self._l['thinking'] if on else '')

    def _save_hist(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(_HIST_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._hist, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _apply_role_tags(self):
        """角色 tag 配置 — 时间线感: Agent 回复呈浅色块, 其余角色着色."""
        t = self.theme
        # 块背景取主题 Checkbutton bg (light #f5f6fa 等, 与正文底色分层)
        block_bg = t.get('Checkbutton', {}).get('bg', '')
        self._txt_chat.tag_configure('ai_user', foreground=t['hint'])
        self._txt_chat.tag_configure('ai_assistant', foreground=t['accent'],
                                     background=block_bg, spacing1=4)
        # 回答正文 (markdown 渲染) — 与辅助行同浅缩进, 挂在 "Agent:" 之下
        self._txt_chat.tag_configure('ai_body', foreground=t['accent'],
                                     background=block_bg,
                                     lmargin1=16, lmargin2=16)
        # 辅助行 (工具行/tokens/时间线/提示/引导) 统一 tag 级缩进 16px
        # — 不用字面空格: 复制不带空格, 换行不脱节, 全员对齐
        self._txt_chat.tag_configure('ai_tool_detail', foreground=t['hint'],
                                     lmargin1=16, lmargin2=16)
        # 工具行展开内容专用 — 缩进加深一级表层级从属
        self._txt_chat.tag_configure('tool_detail_body',
                                     foreground=t['hint'],
                                     lmargin1=32, lmargin2=32)
        # 轮次结算行 (tokens/时间线/已停止/提示) — 顶格页脚, 区隔轮次
        self._txt_chat.tag_configure('ai_meta', foreground=t['hint'])
        self._txt_chat.tag_configure('ai_err', foreground=t['danger'])

    def _on_theme_changed(self, _name=None):
        """主题切换时刷新 markdown tag 与角色块颜色."""
        self._txt_chat.apply_theme(self.app.current_theme_name)
        self._apply_role_tags()

    # 带背景的 tag — Tk 中 tag 背景会盖住选中高亮, 选中期间临时清除
    _BG_TAGS = ('ai_user', 'ai_assistant', 'ai_body', 'ai_tool_detail', 'tool_detail_body', 'ai_meta', 'ai_err',
                'md_code', 'md_code_block', 'md_table', 'md_quote', 'md_quote_2', 'md_quote_3')

    def _on_sel_change(self, _event=None):
        """选中期间清除带背景 tag 的背景, 让选中高亮可见; 取消后恢复."""
        w = self._txt_chat
        if w.tag_ranges('sel'):
            for tag in self._BG_TAGS:
                try:
                    w.tag_configure(tag, background='')
                except tk.TclError as e:
                    pass
        else:
            self._on_theme_changed()

    @staticmethod
    def _on_chat_key(event):
        """聊天区键盘拦截 — 禁止编辑, 放行 Ctrl+C/A 与导航键 (滚动/键盘选择)."""
        if (event.state & 0x4) and event.keysym.lower() in ('c', 'a'):
            return None
        if event.keysym in ('Left', 'Right', 'Up', 'Down',
                            'Home', 'End', 'Prior', 'Next'):
            return None
        return 'break'

    def _build_ui(self):
        t, l = self.theme, self._l

        # 配置行: 端点 / 模型 …… 设置 (最右)
        cfg_bar = self.components.Frame(self, bg=t['bar'])
        cfg_bar.pack(fill=tk.X, padx=8, pady=(8, 0))
        self.components.Label(cfg_bar, bg=t['bar'], text=l['base_url'],
                              fg=t['hint'], padx=0).pack(side=tk.LEFT, padx=0)
        # 服务商下拉 — 项来自配置文件的 providers; 选择即生效并自动匹配 key
        self._cfg_provider = self.components.Combobox(
            cfg_bar, width=40, font=self.components.mono_font(9), values=(),
            state='readonly')
        self._cfg_provider.pack(side=tk.LEFT, padx=(4, 10), ipady=2)
        self._cfg_provider.bind('<<ComboboxSelected>>', self._on_provider_selected)
        self.components.Label(cfg_bar, bg=t['bar'], text=l['model'],
                              fg=t['hint']).pack(side=tk.LEFT)
        # 模型下拉 — 项来自配置文件指定provider的 models; 选择即生效并自动匹配 key
        self._cfg_model = self.components.Combobox(
            cfg_bar, font=self.components.mono_font(9), values=(),
            state='readonly')
        self._cfg_model.pack(side=tk.LEFT, padx=(4, 10), ipady=2)
        self._cfg_model.bind('<<ComboboxSelected>>', self._on_model_selected)

        self.components.Button(cfg_bar, text=l['settings'], pady=1,
                               command=self._open_settings).pack(side=tk.RIGHT)

        # 聊天区 (独立 Frame — 滚动条 pack 在容器内, 不占用窗口级布局)
        # 底部 pady=0: 状态栏紧贴其下缘, 视觉上作为输出框的一部分
        chat_frame = self.components.Frame(self, bg=t['bar'])
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 0))
        self._txt_chat = self.components.MarkdownText(
            chat_frame, theme_name=self.app.current_theme_name,
            selectforeground=t['Text']['bg'], selectbackground=t['Text']['fg'])
        self._txt_chat.pack(fill=tk.BOTH, expand=True, padx=(0, 8))
        self._apply_role_tags()
        # 保持可编辑态以支持鼠标选择复制; 键盘输入全部拦截 (放行 Ctrl+C/A)
        self._txt_chat.bind('<Key>', self._on_chat_key)
        self._txt_chat.config(insertwidth=0)
        # 带背景的 tag 会盖住选中高亮 (Tk 已知行为) — 选中期间临时清背景
        self._txt_chat.bind('<<Selection>>', self._on_sel_change)

        # 状态栏: 与输出区共用 chat_frame (pack 在 Text 之后, 占底部一条) —
        # 视觉上是输出框的内置底条, 滚动条仅框住文本区 (编辑器式布局);
        # 左侧"思考中…"等阶段状态, 右侧上轮/累计 token 消耗
        chat_bg = self._txt_chat.cget('bg')
        status_bar = self.components.Frame(chat_frame, bg=chat_bg, height=24)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)
        self._lbl_status = self.components.Label(
            status_bar, bg=chat_bg, fg=t['hint'], text='')
        self._lbl_status.pack(side=tk.LEFT, padx=8)
        self._lbl_tokens = self.components.Label(
            status_bar, bg=chat_bg, fg=t['hint'], text='')
        self._lbl_tokens.pack(side=tk.RIGHT, padx=8)

        # 输入区 (独立 Frame, 同上) — 与状态栏间隔拉大, 视觉分组
        input_frame = self.components.Frame(self, bg=t['bar'], height=32)
        input_frame.pack(fill=tk.X, padx=8, pady=(8, 0))
        self._txt_input = self._make_scrollable_text(input_frame, height=5)
        self._txt_input.pack(fill=tk.X, padx=(0, 8))
        # self._txt_input.bind('<Control-Return>', lambda _e: self._try_send())
        # 绑定Ctrl/Shit + Return 的功能，不然会被Return触发
        self._txt_input.bind('<Shift-Return>', lambda _e: None)
        self._txt_input.bind('<Control-Return>', lambda _e: None)
        self._txt_input.bind('<Return>', self._on_input_return)
        # 上下箭头历史回填 (仅光标在首/末行时); 实际编辑退出历史浏览
        self._txt_input.bind('<Up>', self._on_input_hist)
        self._txt_input.bind('<Down>', self._on_input_hist)
        self._txt_input.bind('<Key>', self._on_input_edit)

        # bar 贴窗口边缘；bar 内按钮自带右 8 边距（与上方内容区右缘对齐）
        bottom = self.components.Frame(self, bg=t['bar'], height=32)
        # bottom.pack(fill=tk.X, side=tk.BOTTOM, padx=8, pady=(0, 4))
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        bottom.pack_propagate(False)
        self.components.Button(bottom, text=l['clear_chat'], pady=2,
                               command=self._clear_chat).pack(side=tk.LEFT, padx=8, pady=4)
        # RIGHT 侧先 pack 的贴右缘: 发送最右, 勾选在其左
        self._btn_send = self.components.Button(
            bottom, text=l['send'], pady=2, command=self._send)
        self._btn_send.pack(side=tk.RIGHT, padx=8, pady=4)
        
        # 回车发送 — 勾选后 Enter 直接发送 (换行用 Shift+Enter);
        # 未勾选保持原行为 (Ctrl+Enter 或点发送按钮)
        self._enter_send = tk.BooleanVar(value=True)
        self.components.Checkbutton(
            bottom, text=l['enter_send'], variable=self._enter_send,
            bg=t['bar'], selectcolor=t['bar']).pack(side=tk.RIGHT, pady=2, padx=(0, 10))

        # 是否优先本地匹配（不支持上下文，但可以离线使用部分功能）
        self._local_first = tk.BooleanVar(value=True)
        self.components.Checkbutton(
            bottom, text=l['local_first'], variable=self._local_first,
            bg=t['bar'], selectcolor=t['bar']).pack(side=tk.RIGHT, pady=2, padx=(0, 6))
        self._local_first.trace_add('write', lambda *_: self._on_local_first_check())

        # 是否携带上下文
        self._carry = tk.BooleanVar(value=True)
        self.components.Checkbutton(
            bottom, text=l['carry_ctx'], variable=self._carry,
            bg=t['bar'], selectcolor=t['bar']).pack(side=tk.RIGHT, pady=2, padx=(0, 6))

        # 代理下拉 (Menubutton 样式同审查器刷新时间): 无代理/检测到的地址
        self._proxy_var = tk.StringVar(value='')
        self._proxy_btn = self.components.Menubutton(
            bottom, bg=t['bar'], fg=t['fg'], font=self.components.mono_font(9),
            relief=tk.FLAT, padx=6, pady=1, borderwidth=0,
            activebackground=t['hover'], activeforeground=t['fg'],
            cursor='hand2')
        self._proxy_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=4)
        # 菜单只建一次 — 每次新建会向 master.children 注册且替换后不释放,
        # 刷新改为清空重加菜单项 (防稳态泄漏)
        self._proxy_menu = self.components.Menu(
            self._proxy_btn,
            activebackground=t['accent'], activeforeground=t['accent_fg'])
        self._proxy_btn.configure(menu=self._proxy_menu)
        self._proxy_var.trace_add(
            'write', lambda *_: self._proxy_btn.configure(
                text='%s ▾' % self._proxy_display(self._proxy_var.get())))
        self.components.Label(bottom, bg=t['bar'], fg=t['hint'],
                              text=l['proxy']).pack(side=tk.RIGHT)
        self._refresh_proxy()

    def _on_local_first_check(self, *_):
        if self._local_first.get():
            self._append_chat(self._l['local_first_help'] + '\n', 'ai_user')
        else:
            self._append_chat(self._l['local_not_first_help'] + '\n', 'ai_user')

    def on_destroy(self):
        """面板销毁 — 取消 pending 的攒批刷新, 防回调操作已销毁的部件."""
        if self._after_job is not None:
            try:
                self.after_cancel(self._after_job)
            except Exception:
                pass
            self._after_job = None
        self._pending = []

    # ---- 配置 ----

    def _proxy_display(self, value):
        """代理值 → 显示文本 ('none' 显示为本地化"无代理")."""
        return self._l['proxy_none'] if value == 'none' else value

    def _refresh_proxy(self):
        """代理菜单重建 — 本地检测 (环境变量+注册表), 打开时与配置更新后各调一次.

        可选项: 无代理 + 检测到的全部代理地址; 配置为 system 时
        选中检测到的首个地址 (语义等价), 未检测到则选中无代理。
        """
        detected = list_detected_proxies()
        setting = self._config.current.get('proxy', 'system')
        if setting == 'none':
            current = 'none'
        elif setting == 'system':
            current = detected[0] if detected else 'none'
        else:
            current = setting   # 显式地址
            if current not in detected:
                detected.append(current)
        menu = self._proxy_menu
        menu.delete(0, 'end')   # 复用同一菜单, 清空重加 (不新建, 防泄漏)
        menu.add_radiobutton(label=self._l['proxy_none'],
                             variable=self._proxy_var, value='none',
                             command=self._on_proxy_selected)
        for addr in detected:
            menu.add_radiobutton(label=addr, variable=self._proxy_var,
                                 value=addr, command=self._on_proxy_selected)
        self._proxy_var.set(current)   # trace 联动按钮文本

    @staticmethod
    def _get_provider_label(item):
        return f"{item['name']} - {item['url']}"

    def _get_provider_labels(self, providers):
        return [self._get_provider_label(item) for item in providers]

    def _get_provider(self, label):
        name, url = label.split(' - ', 1)
        for provider in self._config.providers:
            if provider['name'] != name or provider['url'] != url:
                continue
            return provider
        return self._config.get_current_provider()

    def _update_combobox(self, providers):
        """设置窗口保存后刷新下拉 (providers 可能已变)."""
        providers = self._config.set_providers(providers)
        self._cfg_provider['values'] = self._get_provider_labels(providers)
        self._cfg_provider.set(self._get_provider_label(self._config.get_current_provider()))
        current_config = self._config.current
        self._cfg_model['values'] = current_config['models']
        self._cfg_model.set(current_config['model'])
        key_source = current_config['key_source']
        names = _SOURCE_ZH if self.app.current_lang_name == 'zh' else _SOURCE_EN
        if key_source:
            self._append_chat(self._l['key_found'] % names.get(key_source, key_source) + '\n', 'ai_user')
        else:
            self._append_chat(self._l['key_not_found'] + '\n', 'ai_user')

    def _on_provider_selected(self, _event=None):
        """端点选择即时生效 — key 由服务端按条目/系统自动匹配."""
        text = self._cfg_provider.get().strip()
        provider = self._get_provider(text)
        if self._config.set_current_provider(provider):
            self._cfg_model['values'] = self._config.current['models']
            current_config = self._config.current
            self._cfg_model.set(current_config['model'])
            key_source = current_config['key_source']
            names = _SOURCE_ZH if self.app.current_lang_name == 'zh' else _SOURCE_EN
            if key_source:
                self._append_chat(self._l['key_found'] % names.get(key_source, key_source) + '\n', 'ai_user')
            else:
                self._append_chat(self._l['key_not_found'] + '\n', 'ai_user')
        self._cfg_provider.selection_clear()

    def _on_model_selected(self, _event=None):
        """模型选择即时生效 — key 由服务端按条目/系统自动匹配."""
        text = self._cfg_model.get().strip()
        self._config.set_current_model(text)
        self._cfg_model.selection_clear()

    def _on_proxy_selected(self, _event=None):
        """代理选择即时生效 — none=直连, 其余为显式代理地址."""
        val = self._proxy_var.get().strip()
        self._config.set_proxy(val)

    # ---- 设置窗口 ----

    def _open_settings(self):
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            self._settings_win.focus_force()
            return
        # 这里传递给AgentSettingsWindo的参数是深拷贝的, 防止直接修改到config
        self._settings_win = AgentSettingsWindow(self, copy.deepcopy(self._config.providers), copy.deepcopy(self._config.DEFAULT_PROVIDERS))
        self._cfg_provider.config(state=tk.DISABLED)
        self._cfg_model.config(state=tk.DISABLED)

    def on_settings_save(self, providers):
        self._update_combobox(providers)

    def on_settings_closed(self):
        self._settings_win = None
        self._cfg_provider.config(state=tk.NORMAL)
        self._cfg_model.config(state=tk.NORMAL)

    def _add_row_tag(self, name, result, summary=None):
        try:
            text = summary or self._summarize_result(result)
            # 折叠行: 点击展开完整结果/收起 — 唯一 tag + 闭包索引
            idx = len(self._tool_rows)
            row_tag = 'tool_row_%d' % idx
            w = self._txt_chat
            w.tag_configure(row_tag, foreground=self.theme['fg'],
                            lmargin1=16, lmargin2=16)   # 与时间线/tokens 行同缩进
            w.tag_bind(row_tag, '<Button-1>',
                        lambda _e, i=idx: self._toggle_tool(i))
            w.tag_bind(row_tag, '<Enter>',
                        lambda _e: w.config(cursor='hand2'))
            w.tag_bind(row_tag, '<Leave>',
                        lambda _e: w.config(cursor=''))
            w.insert(tk.END, '\n▶ ⚙ %s → %s\n' % (name, text), (row_tag,))
            w.see(tk.END)   # 每次输出都跟随到底
            mark_at = 'tool_%d_at' % idx
            # end-1c = 末尾隐含 \n 处 (工具行尾之后); append 实际插在该 \n
            # 之前 (= 锚点处), gravity left 使锚点留在新文本之前 → 钉在行尾
            w.mark_set(mark_at, 'end-1c')
            w.mark_gravity(mark_at, 'left')
            self._tool_rows.append({'result': result, 'open': False,
                                    'tag': row_tag, 'mark_at': mark_at,
                                    'mark_start': 'tool_%d_s' % idx,
                                    'mark_end': 'tool_%d_e' % idx})
        except Exception as e:
            print('add_row_tag err:', str(e))

    # ---- 会话回显 ----

    def _restore_session(self):
        """打开面板时回显服务端会话历史 (上下文仍在, 界面保持一致)."""
        try:
            history = self._svc('get_session') or []
            tool_call_map = {m.get('tool_call_id'): m.get('content', '') for m in history if m and (m or {}).get('role') == 'tool'}
            ai_assistant = False
            for m in history:
                if not m or not isinstance(m, dict):
                    continue
                content = m.get('content', '')
                if not isinstance(content, str):
                    content = ''
                role = (m or {}).get('role')
                if role == 'user':
                    self._append_chat('%s: %s\n' % (self._l['you'], content), 'ai_user')
                    ai_assistant = False
                elif role == 'assistant':
                    # Agent 回复走 markdown 渲染 (与实时输出一致)
                    if not ai_assistant:
                        self._append_chat('%s:\n' % self._l['agent'], 'ai_assistant')
                        ai_assistant = True
                    for tc in m.get('tool_calls', []):
                        fc = tc['function']
                        name = fc['name']
                        result = tool_call_map.get(tc['id'], '')
                        self._add_row_tag(name, result)
                    if content:
                        self._txt_chat.append_markdown(content + '\n', 'ai_body')
                    self._txt_chat.flush()
        except Exception as e:
            print('restore_session err:', str(e))
        self._txt_chat.flush()
        if not history:
            self._show_welcome()

    def _show_welcome(self):
        """无历史时的能力引导 (纯 UI 展示, 不进 session 不耗 token)."""
        self._append_chat(self._l['welcome'] + '\n', 'ai_tool_detail')

    # ---- 服务交互 ----

    def _svc(self, name, *args, **kwargs):
        try:
            return self.app.services.call('agent@' + name, *args, **kwargs)
        except KeyError:
            return None

    # ---- 发送/事件渲染 ----

    def _send(self):
        l = self._l
        if self._btn_send.cget('text') == l['stop']:
            self._stop_current()
            return
        text = self._get_text(self._txt_input).strip()
        if not text:
            self._append_chat(l['err_empty'] + '\n', 'ai_err')
            return
        carry = self._carry.get()
        tid = self._svc('ask', text, carry, win=self, local_first=self._local_first.get())
        if tid is None or tid < 0:
            if tid is not None and tid == -2:
                self._append_chat(l['err_no_api_key'] + '\n', 'ai_err')
                return
            self._append_chat(l['err_no_service'] + '\n', 'ai_err')
            return
        self._task_id = tid
        # 记入输入历史 (相邻去重, 上限截断)
        if not self._hist or self._hist[-1] != text:
            self._hist.append(text)
            self._hist = self._hist[-_HIST_MAX:]
            self._save_hist()
        self._hist_idx = -1
        marker = '' if carry else ' %s' % l['single_turn']
        self._append_chat('\n%s: %s%s\n' % (l['you'], text, marker),
                          'ai_user')
        self._set_editable_text(self._txt_input, '')
        self._btn_send.config(text=l['stop'], bg=self.theme['danger'])
        self._set_thinking(True)
        self._t_send = time.monotonic()
        self._timings = []
        self._append_chat('%s:\n' % l['agent'], 'ai_assistant')

    def _stop_current(self):
        """停止当前任务 — UI 立即复位, 不等 worker 醒来.

        socket 阻塞期间 worker 无法即时响应 stop (最长挂到读超时);
        面板先行复位, worker 醒来后的迟到 done/error 事件因 task_id
        失配被忽略 (session 占位由服务侧 done 分支正常写回)。
        """
        if self._task_id is not None:
            self._svc('stop', self._task_id)
            self._task_id = None
        self._flush_chunks()
        self._txt_chat.flush()   # 渲染流式末段残留 (与 _on_done 一致)
        self._set_thinking(False)
        self._timings = []
        self._append_chat('\n[%s]\n' % self._l['stopped'], 'ai_meta')
        self._btn_send.config(text=self._l['send'],
                              bg=self.theme['Button']['bg'])

    def _on_progress(self, task_id, phase, round_no):
        """阶段进展 — 状态行实时反映所处步骤 (第 N 轮请求/执行工具)."""
        if task_id != self._task_id:
            return
        if phase == 'request':
            self._lbl_status.config(
                text=self._l['waiting_round'] % round_no)

    def _on_tool_call(self, task_id, name, _args):
        if task_id != self._task_id:
            return
        self._lbl_status.config(text=self._l['running_tool'] % name)

    def _on_timing(self, task_id, kind, label, elapsed):
        """耗时事件入缓冲 — 即来即打会把正文切碎 (每轮 3 行), done 时
        由 _timing_line 合成一行紧凑时间线; 实时进展由状态行表达."""
        if task_id != self._task_id:
            return
        self._timings.append((kind, label, elapsed))

    def _timing_line(self):
        """缓冲的耗时事件 → 一行紧凑时间线 (TTFT 并入所属轮次段)."""
        l = self._l
        segs, ttfts = [], {}
        for kind, label, elapsed in self._timings:
            if kind == 'ttft':
                ttfts[label] = elapsed
            elif kind == 'request':
                seg = l['time_round'] % (label, elapsed)
                if label in ttfts:
                    seg += l['time_ttft'] % ttfts.pop(label)
                segs.append(seg)
            else:
                segs.append(l['time_tool'] % (label, elapsed))
        # 只有 TTFT 没有整轮 (请求中途出错等) — 兜底落尾, 不丢信息
        segs.extend(l['time_ttft_lone'] % e for e in ttfts.values())
        total = l['time_total'] % (time.monotonic() - self._t_send)
        return ' · '.join([total] + segs)

    def _on_chunk(self, task_id, text):
        if task_id != self._task_id:
            return
        self._set_thinking(False)   # 首个 chunk 到达, 结束静默期
        self._pending.append(text)
        if self._after_job is None:
            self._after_job = self.after(100, self._flush_chunks)

    def _flush_chunks(self):
        self._after_job = None
        if self._pending:
            text = ''.join(self._pending)
            self._pending = []
            # 段级 Markdown 渲染: 完整段即时渲染, 末段留缓冲
            self._txt_chat.append_markdown(text, 'ai_body')
            self._txt_chat.see(tk.END)   # 每次输出都跟随到底

    def _on_tool_result(self, task_id, name, result, summary=None):
        if task_id != self._task_id:
            return
        self._flush_chunks()   # 先落攒批文本, 保证工具行接在流式输出之后
        self._txt_chat.flush()   # 工具行插入前强制渲染未稳定段
        self._add_row_tag(name, result, summary)
        self._set_thinking(True)   # 工具结果回填模型, 等待下一轮回答

    def _toggle_tool(self, idx):
        """点击工具行: 就地展开完整结果 / 收起; 图标 ▶/▼ 切换.

        展开上限 64KB 纯兜底 — 内置工具不注册后结果普遍 <<1KB, 仅
        fn_ref 自定义工具失控返回超大内容时截断 (Text 渲染 64KB 无压力)。
        """
        row = self._tool_rows[idx]
        w = self._txt_chat
        first = w.tag_ranges(row['tag'])[0]   # 原行恒为 tag 首段
        icon_at = '%s+1c' % first             # '\n▶' 中 ▶ 的偏移
        if row['open']:
            w.delete(row['mark_start'], row['mark_end'])
            w.delete(icon_at, '%s+1c' % icon_at)
            w.insert(icon_at, '▶', (row['tag'],))
            row['open'] = False
            return
        result = row['result']
        if len(result) > 65536:
            result = result[:65536] + '…'
        w.delete(icon_at, '%s+1c' % icon_at)
        w.insert(icon_at, '▼', (row['tag'],))
        # 就地展开: 插入点 = 工具行尾锚点 (mark_at 已被 gravity left 钉住);
        # mark_start 钉内容头, mark_end (right) 随插入移动恒为内容尾
        w.mark_set(row['mark_start'], row['mark_at'])
        w.mark_gravity(row['mark_start'], 'left')
        w.mark_set(row['mark_end'], row['mark_at'])
        w.mark_gravity(row['mark_end'], 'right')
        # 展开内容直接接在工具行下, 缩进加深一级表层级从属 (tag 级
        # 缩进, 选择复制不带空格); 原行图标已切 ▼ 表达可收起
        for line in (result.splitlines() or ['(空)']):
            w.insert(row['mark_end'], '%s\n' % line, ('tool_detail_body',))
        # 短详情首尾同屏; 长详情停在开头, 不再把视图拽到底部
        w.see(row['mark_end'])
        w.see(row['mark_start'])
        row['open'] = True

    @staticmethod
    def _summarize_result(result):
        """摘要缺失时的回退: 首个非空行 ≤120 字符 + 省略标记."""
        text = str(result or '').strip()
        if not text:
            return '(空)'
        line = next((l for l in text.splitlines() if l.strip()), text)
        if len(line) > 120:
            line = line[:120] + '…'
        return line

    def _on_local(self, task_id, text):
        """内置问答单行应答: 内联接在 'Agent:' 同行.

        发送时标签已打印为 'Agent:\\n' 且本地路径此前无任何追加。
        注意缓冲末尾: 'Agent:' + 真实 \\n + Text 隐含 \\n — end-1c 是
        隐含换行处 (真实换行之后, 会插到下一行), end-2c 才是标签行尾。
        """
        if task_id != self._task_id:
            return
        self._txt_chat.insert('end-2c', ' %s' % text, 'ai_assistant')

    def _on_done(self, task_id, text, usage=None):
        if task_id != self._task_id:
            return
        self._flush_chunks()
        self._txt_chat.flush()   # 渲染流式末段残留
        if isinstance(usage, dict):
            # 输入后附命中·命中率 (llm 归一化键; 全零=端点未报缓存, 不显示)
            prompt = usage.get('prompt_tokens', 0)
            completion = usage.get('completion_tokens', 0)
            hit, miss = usage.get('cache_hit', 0), usage.get('cache_miss', 0)
            prompt_s = str(prompt)
            if hit or miss:
                pct = round(100.0 * hit / prompt) if prompt else 0
                prompt_s += self._l['cache_detail'] % (hit, pct)
            line = self._l['tokens'] % (
                usage.get('total_tokens', 0), prompt_s, completion)
            self._append_chat('\n%s\n' % line, 'ai_meta')
            # 状态栏右侧: 累计拆分 (basic_qa 本地应答无 usage, 不更新)
            self._total_tokens += usage.get('total_tokens', 0)
            self._total_hit += hit
            self._total_prompt += prompt
            self._total_completion += completion
            l, fmt = self._l, self._fmt_tokens
            stat = '%s %s [%s %s' % (l['stat_total'],
                                     fmt(self._total_tokens),
                                     l['stat_in'], fmt(self._total_prompt))
            if self._total_hit:
                pct = round(100.0 * self._total_hit / self._total_prompt) \
                    if self._total_prompt else 0
                stat += l['stat_hit_fmt'] % (l['stat_hit'],
                                             fmt(self._total_hit), pct)
            stat += ', %s %s]' % (l['stat_out'],
                                  fmt(self._total_completion))
            self._lbl_tokens.config(text=stat)
        if self._t_send is not None:
            # 内置问答本地命中 (usage='local' 哨兵) 跳过 — 0.0s 纯噪音
            if usage != 'local':
                self._append_chat('%s\n' % self._timing_line(),
                                  'ai_meta')
            self._t_send = None
        self._timings = []
        self._append_chat('\n', 'ai_assistant')
        self._task_id = None
        self._set_thinking(False)
        self._btn_send.config(text=self._l['send'],
                              bg=self.theme['Button']['bg'])

    @staticmethod
    def _fmt_tokens(n):
        """token 数格式化: <1000 完整显示, 否则缩写 k (不用 M — 0.1M 才跳动太粗)."""
        return str(n) if n < 1000 else '%.1fk' % (n / 1000)

    def _on_error(self, task_id, err):
        if task_id != self._task_id:
            return
        self._flush_chunks()
        self._txt_chat.reset()   # 丢弃未渲染的流式残留
        self._append_chat('\n[%s]\n' % err, 'ai_err')
        self._task_id = None
        self._timings = []
        self._set_thinking(False)
        self._btn_send.config(text=self._l['send'],
                              bg=self.theme['Button']['bg'])

    def _append_chat(self, text, tag=None):
        w = self._txt_chat
        w.insert(tk.END, text, tag)
        w.see(tk.END)   # 每次输出都跟随到底

    def _clear_chat(self):
        l = self._l
        # 清空不可逆 (磁盘会话文件被覆盖) — 弹窗确认
        if not self.components.askyesno(l['title'], l['confirm_clear'],
                                        parent=self):
            return
        # 服务端会先终止进行中的提问, 面板按钮经 done 事件自动复位
        self._svc('clear_session')
        w = self._txt_chat
        w.delete('1.0', tk.END)
        w.reset()   # 清 markdown 缓冲与代码块状态 (delete 已销毁嵌入按钮)
        # Tk tag/mark 在文本删除后仍存活 — 显式释放, 防高水位平台期占用
        for row in self._tool_rows:
            try:
                w.tag_delete(row['tag'])
                w.mark_unset(row['mark_at'])
                w.mark_unset(row['mark_start'])
                w.mark_unset(row['mark_end'])
            except tk.TclError:
                pass
        self._tool_rows = []   # 折叠行状态随内容清空
        self._show_welcome()   # 清空=重新开始, 重新给出能力引导
        self._on_local_first_check()
