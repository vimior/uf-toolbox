# -*- coding: utf-8 -*-
"""Theme-aware UI components — exposed as app.components / self.components.

每个方法都是对应 tkinter 控件的薄包装: 默认样式来自
``app.theme['<控件名>']``（见 themes/dark.py、themes/light.py 的
PascalCase 键），调用方传入的参数覆盖主题默认值.
字体统一在此补充 (FONT_FAMILY, size)，不写在主题文件里.

未包装的控件 (Canvas、StringVar 等) 经 __getattr__ 转发给 tkinter.
"""
import tkinter as tk
from tkinter import ttk

from ..common import FONT_FAMILY, MONO_FAMILY
from .scrollbar import AutoHideScrollbar
from .scrollable_text import ScrollableText
from .scrollable_canvas import ScrollableCanvas
from .scrollable_listbox import ScrollableListbox
from .theme_toplevel import AppToplevel


#: 控件默认字体 (主题不定义字体，统一在此补充；仅字体控件)
_FONT_SIZE = {
    'Menu': (FONT_FAMILY, 11),
}
_DEFAULT_FONT = (FONT_FAMILY, 9)
_FONTABLE = {'Button', 'Label', 'Entry', 'Spinbox', 'Listbox', 'Text',
             'Checkbutton', 'Radiobutton', 'Menu', 'Menubutton'}

#: 主题控件组中仅作语义用 (如 Button.disabled_bg), 不传给 tkinter 的键
_NON_WIDGET_KEYS = {'disabled_bg'}


class Components:
    def __init__(self, app):
        self._app = app
        self._combo_theme = None   # 上次配置 combo 样式的主题名
        self._combos = []          # 已创建的 Combobox 实例 (刷新 popdown 用)

    def __getattr__(self, name):
        """Fallback: forward any undefined name to the tkinter module.

        e.g. self.components.Canvas(...) works even though Components only
        defines themed wrappers for some widgets.
        """
        return getattr(tk, name)

    # ---- helpers ----

    def _defaults(self, name, kwargs):
        """Theme defaults for widget *name*, overridden by caller kwargs."""
        d = dict(self._app.theme.get(name, {}))
        if name in _FONTABLE:
            d.setdefault('font', _FONT_SIZE.get(name, _DEFAULT_FONT))
        d.update(kwargs)
        for k in _NON_WIDGET_KEYS:
            d.pop(k, None)
        return d

    def font(self, size, *styles):
        """生成标准 tkinter 字体元组 (FONT_FAMILY, size, *styles)

        参数与原生 tkinter 完全一致, 仅免写家族名：
        ``self.components.font(12, 'bold')`` -> (FONT_FAMILY, 12, 'bold')
        """
        return (FONT_FAMILY, size) + tuple(styles)

    def mono_font(self, size, *styles):
        """生成等宽字体元组 (MONO_FAMILY, size, *styles) — 列对齐场景用.

        家族名按平台取 (Consolas / Menlo / DejaVu Sans Mono)：
        ``self.components.mono_font(9, 'bold')`` -> (MONO_FAMILY, 9, 'bold')
        """
        return (MONO_FAMILY, size) + tuple(styles)

    def _configure_combo_style(self):
        """Configure the fixed ttk style 'combo' — re-configured per theme.

        固定命名样式 + 主题名缓存: 主题切换后首次调用重新配置同一样式,
        旧样式不留存 (避免 combo_<theme> 只增不清理的命名样式泄漏).
        """
        style_name = 'combo'
        if self._combo_theme == self._app.current_theme_name:
            return style_name
        self._combo_theme = self._app.current_theme_name
        style = self._app.ttk_style
        # 命名样式必须自带 layout (继承 TCombobox 的布局);
        # 边框宽度由布局 field 的 -border 控制: style 的 borderwidth 对
        # Combobox 无效 (Tk 硬编码 1px), 只有布局选项真正影响渲染
        layout = style.layout('TCombobox')
        c = self._app.theme['Combobox']
        for elem, opts in layout:
            if elem == 'Combobox.field':
                opts['border'] = c.get('border', 0)
        style.layout(style_name, layout)
        style.configure(
            style_name,
            fieldbackground=c['fieldbackground'],
            background=c['background'],
            foreground=c['foreground'],
            selectbackground=c['selectbackground'],
            arrowcolor=c['arrowcolor'],
            # 细边框 + 暗色 (lightcolor/darkcolor 控制边框颜色);
            # .get 回退保证旧配置/第三方主题不传新字段时仍可用
            borderwidth=c.get('borderwidth', 1),
            lightcolor=c.get('lightcolor', self._app.theme['border']),
            darkcolor=c.get('darkcolor', self._app.theme['border']),
        )
        return style_name

    def refresh_combo_style(self):
        """强制按当前主题重配 'combo' 样式并刷新已创建的下拉列表
        (主题切换时由 set_theme 调用).

        - ttk 命名样式共享: configure 后所有引用 'combo' 的实例立即更新.
        - popdown 下拉列表是首次展开时才创建的 tk.Listbox, option_add 不会
          影响已创建的实例 — 需直接 config 刷新 (bg/fg/选中项).
        """
        self._combo_theme = None
        self._configure_combo_style()
        self.refresh_combobox_popdowns()

    def refresh_combobox_popdowns(self):
        """刷新所有已创建 Combobox 的下拉列表颜色 (主题切换后调用).

        popdown 是 Tcl 端懒创建的 (首次展开时), 路径规律为
        ``<combo>.popdown.f.l`` (tk.Listbox)。未展开过的 combo 跳过 —
        其首次展开时读 option_add (已在主题切换时更新), 颜色即正确。
        """
        t = self._app.theme
        c = t['Combobox']
        sel_fg = t['accent_fg']
        alive = []
        for combo in self._combos:
            if not combo.winfo_exists():
                continue
            alive.append(combo)
            lb = combo._w + '.popdown.f.l'
            if not combo.tk.call('winfo', 'exists', lb):
                continue
            combo.tk.call(lb, 'configure',
                          '-background', c['fieldbackground'],
                          '-foreground', c['foreground'],
                          '-selectbackground', c['selectbackground'],
                          '-selectforeground', sel_fg)
        self._combos = alive

    @staticmethod
    def _bind_active(d, kwargs):
        """active 状态视觉跟随显式 bg/fg (未显式传 active 时).

        避免点击后 (模态弹窗吞掉 release 事件) 控件 stuck 在 active
        状态导致颜色突变.
        """
        if 'bg' in kwargs and 'activebackground' not in kwargs:
            d['activebackground'] = kwargs['bg']
        if 'fg' in kwargs and 'activeforeground' not in kwargs:
            d['activeforeground'] = kwargs['fg']

    # ---- simple wrappers ----

    def Button(self, master, **kwargs):
        """tk.Button — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Button', kwargs)
        self._bind_active(d, kwargs)
        return tk.Button(master, **d)

    def Label(self, master, **kwargs):
        return tk.Label(master, **self._defaults('Label', kwargs))

    def Entry(self, master, **kwargs):
        return tk.Entry(master, **self._defaults('Entry', kwargs))

    def Spinbox(self, master, **kwargs):
        """tk.Spinbox — 默认样式来自主题 Spinbox 组 (对齐 Entry 模式)."""
        return tk.Spinbox(master, **self._defaults('Spinbox', kwargs))

    def Menubutton(self, master, **kwargs):
        """tk.Menubutton — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Menubutton', kwargs)
        self._bind_active(d, kwargs)
        return tk.Menubutton(master, **d)

    def Frame(self, master, **kwargs):
        return tk.Frame(master, **self._defaults('Frame', kwargs))

    def Toplevel(self, master=None, **kwargs):
        """主题感知 Toplevel (AppToplevel) — 默认 bg 来自主题 Toplevel 键.

        防闪烁/隐藏启动/自动图标见 common.components.theme_toplevel.
        """
        return AppToplevel(master, app=self._app, **kwargs)

    def Checkbutton(self, master, **kwargs):
        """tk.Checkbutton — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Checkbutton', kwargs)
        self._bind_active(d, kwargs)
        return tk.Checkbutton(master, **d)

    def Radiobutton(self, master, **kwargs):
        """tk.Radiobutton — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Radiobutton', kwargs)
        self._bind_active(d, kwargs)
        return tk.Radiobutton(master, **d)

    def Listbox(self, master, **kwargs):
        return tk.Listbox(master, **self._defaults('Listbox', kwargs))

    def Separator(self, master, **kwargs):
        """Thin horizontal divider line (Frame, height=1)."""
        return tk.Frame(master, **self._defaults('Separator', kwargs))

    def Card(self, master, **kwargs):
        """Container with card background + subtle border."""
        return tk.Frame(master, **self._defaults('Card', kwargs))

    def Menu(self, master=None, **kwargs):
        return tk.Menu(master, **self._defaults('Menu', kwargs))

    def Combobox(self, master, **kwargs):
        """ttk.Combobox themed via the 'combo' style.

        默认样式来自主题 Combobox 键; 调用方参数可覆盖 (含 font——
        ttk 动态选项实际参与渲染, 等宽对齐可直接传 font)
        """
        kwargs.setdefault('style', self._configure_combo_style())
        combo = ttk.Combobox(master, **kwargs)
        self._combos.append(combo)   # 登记以便主题切换时刷新 popdown
        return combo

    def Scrollbar(self, master, auto_hide=True, **kwargs):
        """tk.Scrollbar — themed, with auto-hide.

        *auto_hide*=False 返回普通 tk.Scrollbar (常驻，无布局抖动)
        """
        kwargs.setdefault('orient', tk.VERTICAL)
        d = self._defaults('Scrollbar', kwargs)
        if auto_hide:
            return AutoHideScrollbar(master, **d)
        return tk.Scrollbar(master, **d)

    # ---- message-style dialogs ----

    _DIALOG_ICONS = {'info': '✓', 'warn': '⚠', 'error': '✕', 'question': '?'}
    _DIALOG_COLORS = {'info': 'success', 'warn': 'warn',
                      'error': 'danger', 'question': 'accent'}
    _BTN_TEXTS = {
        'zh': {'ok': '确定', 'yes': '是', 'no': '否', 'cancel': '取消'},
        'en': {'ok': 'OK', 'yes': 'Yes', 'no': 'No', 'cancel': 'Cancel'},
    }

    def _btn_text(self, key):
        lang = getattr(self._app, 'current_lang_name', 'en')
        return self._BTN_TEXTS.get(lang, self._BTN_TEXTS['en']).get(key, key)

    def _dialog(self, parent, title, message, kind='info',
                buttons=('ok',), default=None):
        """主题化模态对话框 — 居中于 *parent*, 返回被点击的按钮标识。

        *buttons*: 从左到右显示的按钮标识 (ok/yes/no/cancel);
        *default*: 主按钮 (最右, Esc/关闭窗口等价于点击它), 缺省取末位。
        """
        s = self._app.theme
        if default not in buttons:
            default = buttons[-1]
        icon = self._DIALOG_ICONS.get(kind, '•')
        color = s[self._DIALOG_COLORS.get(kind, 'fg')]

        dlg = self.Toplevel(parent)
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(parent)
        dlg.configure(bg=s['card'])

        body = self.Frame(dlg, bg=s['card'])
        body.pack(padx=24, pady=(20, 12))
        self.Label(body, text=icon, font=self.font(30),
                   fg=color, bg=s['card']).pack(side=tk.LEFT, padx=(0, 12))
        self.Label(body, text=message, font=self.font(10),
                   bg=s['card'], justify=tk.LEFT,
                   wraplength=320).pack(side=tk.LEFT, anchor='n')

        # 按钮栏: 紧贴窗口底部, 占满整行; 按钮均分整行宽度, 之间留间隔
        btn_frame = self.Frame(dlg, bg=s['card'])
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)

        result = {}

        def finish(r):
            result['r'] = r
            dlg.destroy()

        # 从左到右按 *buttons* 顺序排列 (与原生 messagebox 一致).
        # 视觉: 末位按钮 (语义主操作 "是"/"确定") 实心强调色 + 粗体,
        #       其余描边; *default* 仅控制 focus 与 Esc/关闭等价 (安全默认)
        default_btn = None
        for i, b in enumerate(buttons):
            if b == buttons[-1]:
                # 主按钮 (语义主操作): 强调色实心 + 粗体
                btn = self.Button(btn_frame, text=self._btn_text(b),
                                  command=lambda r=b: finish(r),
                                  bg=s['accent'], fg=s['accent_fg'],
                                  font=self.font(9, 'bold'))
            else:
                # 次按钮: 对话框底色 + 细描边
                btn = self.Button(btn_frame, text=self._btn_text(b),
                                  command=lambda r=b: finish(r),
                                  bg=s['card'], fg=s['fg'],
                                  highlightbackground=s['sep'],
                                  highlightthickness=1)
            if b == default:
                default_btn = btn
            # 首尾按钮外缘边距 8, 按钮间间隔 8
            padx = (8, 4) if i == 0 else ((4, 8) if i == len(buttons) - 1
                                          else (4, 4))
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=padx)
        dlg.protocol('WM_DELETE_WINDOW', lambda: finish(default))
        dlg.bind('<Escape>', lambda e: finish(default))
        if default == buttons[-1]:
            # default 是实心主按钮, 不持焦; Return 兜底触发
            # (焦点在按钮上时由按钮自身处理, 避免双触发)
            dlg.bind('<Return>', lambda e: finish(default)
                     if dlg.focus_get() is dlg else None)

        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        # 先按请求尺寸粗定位 (避免首帧闪烁), 显示后补偿装饰偏移精确居中
        px = parent.winfo_rootx() + (parent.winfo_width() - dw) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - dh) // 2
        dlg.geometry(f'{dw}x{dh}+{px}+{py}')
        dlg.deiconify()
        dlg.update_idletasks()
        # Windows 窗口管理器给 geometry 位置附加装饰偏移 (标题栏/边框),
        # 导致窗口偏下偏右; 实测偏移后反推补偿, 使内容区真正居中.
        # 注: 目标位置超出屏幕时会被窗口管理器钳制, 无法完全居中属正常.
        off_x = dlg.winfo_rootx() - px
        off_y = dlg.winfo_rooty() - py
        tx = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_width()) // 2 - off_x
        ty = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 2 - off_y
        dlg.geometry(f'+{tx}+{ty}')
        dlg.grab_set()
        dlg.focus_force()
        # 窗口显示后按钮才可取得焦点 (withdrawn 状态 focus_set 无效).
        # 实心(末位)按钮不持焦, 避免虚线焦点框; 仅描边 default 持焦
        if default_btn is not None and default != buttons[-1]:
            default_btn.focus_set()
        dlg.wait_window(dlg)
        return result.get('r', default)

    def showinfo(self, parent, title, message):
        """Info dialog — same semantics as ``messagebox.showinfo``."""
        self._dialog(parent, title, message, kind='info', buttons=('ok',))

    def showwarn(self, parent, title, message):
        """Warning dialog — same semantics as ``messagebox.showwarning``."""
        self._dialog(parent, title, message, kind='warn', buttons=('ok',))

    def showerror(self, parent, title, message):
        """Error dialog — same semantics as ``messagebox.showerror``."""
        self._dialog(parent, title, message, kind='error', buttons=('ok',))

    def askyesno(self, parent, title, message):
        """Yes/No dialog — returns True for yes, False otherwise."""
        return self._dialog(parent, title, message, kind='question',
                            buttons=('no', 'yes'), default='no') == 'yes'

    def askyesnocancel(self, parent, title, message):
        """Yes/No/Cancel dialog — returns 'yes' | 'no' | None (cancel)."""
        r = self._dialog(parent, title, message, kind='question',
                         buttons=('cancel', 'no', 'yes'), default='no')
        return None if r == 'cancel' else r

    def askquestion(self, parent, title, message):
        """Yes/No dialog — returns 'yes' or 'no' (default yes)."""
        return self._dialog(parent, title, message, kind='question',
                            buttons=('no', 'yes'), default='yes')

    # ---- scrollable containers ----

    def ScrollableText(self, master, scrollbars='y', auto_hide=True, **kwargs):
        """Text with built-in themed scrollbars (auto-hiding by default).

        Content changes (insert/delete) and layout changes auto-update the
        scrollbar visibility — no attach/polling needed. Pack the returned
        Text as usual; the scrollbars are laid out automatically.

        *scrollbars*: 'y' (vertical only, default), 'x', or 'both'.
        *auto_hide*=False: 滚动条常驻 (无 pack 抖动)
        """
        d = self._defaults('Text', kwargs)
        # 保留原默认等宽字体 (阶段 3 统一为 mono_font 入口时再调整)
        d['font'] = kwargs.get('font', ('Consolas', 9))
        sb_y = (self.Scrollbar(master, auto_hide=auto_hide)
                if scrollbars in ('y', 'both') else None)
        sb_x = (self.Scrollbar(master, orient=tk.HORIZONTAL,
                               auto_hide=auto_hide)
                if scrollbars in ('x', 'both') else None)
        txt = ScrollableText(master, sb_y, sb_x, **d)
        if sb_y is not None:
            txt.configure(yscrollcommand=sb_y.set)
            sb_y.config(command=txt.yview)
        if sb_x is not None:
            txt.configure(xscrollcommand=sb_x.set)
            sb_x.config(command=txt.xview)
        return txt

    def ScrollableCanvas(self, master, scrollbars='y', auto_hide=True, **kwargs):
        """Canvas with built-in themed scrollbars (auto-hiding by default).

        Content lives in the returned canvas's ``inner`` Frame; its
        <Configure> drives scrollregion + scrollbar visibility — no
        attach/polling needed. Pack the returned Canvas as usual.

        *scrollbars*: 'y' (vertical only, default), 'x', or 'both'.
        *auto_hide*=False: 滚动条常驻 (无 pack 抖动)
        """
        d = dict(self._app.theme.get('Frame', {}))
        d.setdefault('highlightthickness', 0)
        d.setdefault('borderwidth', 0)
        d.update(kwargs)
        sb_y = (self.Scrollbar(master, auto_hide=auto_hide)
                if scrollbars in ('y', 'both') else None)
        sb_x = (self.Scrollbar(master, orient=tk.HORIZONTAL,
                               auto_hide=auto_hide)
                if scrollbars in ('x', 'both') else None)
        cv = ScrollableCanvas(master, sb_y, sb_x, **d)
        if sb_y is not None:
            cv.configure(yscrollcommand=sb_y.set)
            sb_y.config(command=cv.yview)
        if sb_x is not None:
            cv.configure(xscrollcommand=sb_x.set)
            sb_x.config(command=cv.xview)
        return cv

    def ScrollableListbox(self, master, **kwargs):
        """Listbox with a built-in auto-hiding themed vertical scrollbar.

        Content changes (insert/delete) and layout changes auto-update the
        scrollbar visibility — no attach/polling needed. Pack the returned
        Listbox as usual; the scrollbar is laid out automatically.
        """
        d = self._defaults('Listbox', kwargs)
        sb = self.Scrollbar(master)
        lb = ScrollableListbox(master, sb, **d)
        lb.configure(yscrollcommand=sb.set)
        sb.config(command=lb.yview)
        return lb
