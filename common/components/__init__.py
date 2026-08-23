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
from .markdown_text import MarkdownText, MD_COLORS


#: 控件默认字体 (主题不定义字体，统一在此补充；仅字体控件)
_FONT_SIZE = {
    'Menu': (FONT_FAMILY, 11),
}
_DEFAULT_FONT = (FONT_FAMILY, 9)
# Text 不在 _FONTABLE: 其默认字体由 ScrollableText 自行 setdefault
# (等宽 Consolas), 若在 _FONTABLE 会先补 _DEFAULT_FONT 抢占该默认
_FONTABLE = {'Button', 'Label', 'Entry', 'Spinbox', 'Listbox',
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

    def _defaults(self, name, kwargs, cnf=None):
        """Theme defaults for widget *name*, overridden by caller kwargs.

        *cnf* 为原生第二位置参数 (dict)；优先级: 主题 < cnf < kwargs
        (与原生 cnf/kw 合并语义一致).
        """
        d = dict(self._app.theme.get(name, {}))
        if name in _FONTABLE:
            d.setdefault('font', _FONT_SIZE.get(name, _DEFAULT_FONT))
        if cnf:
            d.update(cnf)
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
    def _bind_active(d, explicit):
        """active 状态视觉跟随显式 bg/fg (未显式传 active 时).

        避免点击后 (模态弹窗吞掉 release 事件) 控件 stuck 在 active
        状态导致颜色突变.  *explicit* = cnf + kwargs 合并后的调用方参数.
        """
        if 'bg' in explicit and 'activebackground' not in explicit:
            d['activebackground'] = explicit['bg']
        if 'fg' in explicit and 'activeforeground' not in explicit:
            d['activeforeground'] = explicit['fg']

    # ---- simple wrappers ----

    # 签名与原生 tkinter 完全一致: (master=None, cnf={}, **kw);
    # cnf/kw 均覆盖主题默认 (kw 优先, 与原生 cnf/kw 合并语义一致).

    def Button(self, master=None, cnf={}, **kwargs):
        """tk.Button — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Button', kwargs, cnf)
        explicit = dict(cnf)
        explicit.update(kwargs)
        self._bind_active(d, explicit)
        return tk.Button(master, **d)

    def Label(self, master=None, cnf={}, **kwargs):
        return tk.Label(master, **self._defaults('Label', kwargs, cnf))

    def Entry(self, master=None, cnf={}, **kwargs):
        return tk.Entry(master, **self._defaults('Entry', kwargs, cnf))

    def Spinbox(self, master=None, cnf={}, **kwargs):
        """tk.Spinbox — 默认样式来自主题 Spinbox 组 (对齐 Entry 模式)."""
        return tk.Spinbox(master, **self._defaults('Spinbox', kwargs, cnf))

    def Menubutton(self, master=None, cnf={}, **kwargs):
        """tk.Menubutton — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Menubutton', kwargs, cnf)
        explicit = dict(cnf)
        explicit.update(kwargs)
        self._bind_active(d, explicit)
        return tk.Menubutton(master, **d)

    def Frame(self, master=None, cnf={}, **kwargs):
        return tk.Frame(master, **self._defaults('Frame', kwargs, cnf))

    def Toplevel(self, master=None, cnf={}, **kwargs):
        """主题感知 Toplevel (AppToplevel) — 默认 bg 来自主题 Toplevel 键.

        防闪烁/隐藏启动/自动图标见 common.components.theme_toplevel.
        """
        return AppToplevel(master, cnf=cnf, app=self._app, **kwargs)

    def Checkbutton(self, master=None, cnf={}, **kwargs):
        """tk.Checkbutton — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Checkbutton', kwargs, cnf)
        explicit = dict(cnf)
        explicit.update(kwargs)
        self._bind_active(d, explicit)
        return tk.Checkbutton(master, **d)

    def Radiobutton(self, master=None, cnf={}, **kwargs):
        """tk.Radiobutton — active 状态视觉跟随显式 bg/fg (见 _bind_active)."""
        d = self._defaults('Radiobutton', kwargs, cnf)
        explicit = dict(cnf)
        explicit.update(kwargs)
        self._bind_active(d, explicit)
        return tk.Radiobutton(master, **d)

    def Listbox(self, master=None, cnf={}, **kwargs):
        return tk.Listbox(master, **self._defaults('Listbox', kwargs, cnf))

    def Separator(self, master=None, cnf={}, **kwargs):
        """Thin horizontal divider line (Frame, height=1)."""
        return tk.Frame(master, **self._defaults('Separator', kwargs, cnf))

    def Card(self, master=None, cnf={}, **kwargs):
        """Container with card background + subtle border."""
        return tk.Frame(master, **self._defaults('Card', kwargs, cnf))

    def Menu(self, master=None, cnf={}, **kwargs):
        return tk.Menu(master, **self._defaults('Menu', kwargs, cnf))

    def Combobox(self, master=None, **kwargs):
        """ttk.Combobox themed via the 'combo' style.

        默认样式来自主题 Combobox 键; 调用方参数可覆盖 (含 font——
        ttk 动态选项实际参与渲染, 等宽对齐可直接传 font)
        """
        kwargs.setdefault('style', self._configure_combo_style())
        combo = ttk.Combobox(master, **kwargs)
        # ttk readonly combo 选中后文本保持高亮 — 选择后清除选中态
        combo.bind('<<ComboboxSelected>>', lambda _e: combo.selection_clear())
        self._combos.append(combo)   # 登记以便主题切换时刷新 popdown
        return combo

    def Scrollbar(self, master=None, cnf={}, **kwargs):
        """tk.Scrollbar — themed, with auto-hide.

        *auto_hide*=False 返回普通 tk.Scrollbar (常驻，无布局抖动)
        """
        auto_hide = kwargs.pop('auto_hide', True)
        kwargs.setdefault('orient', tk.VERTICAL)
        d = self._defaults('Scrollbar', kwargs, cnf)
        if auto_hide:
            return AutoHideScrollbar(master, **d)
        return tk.Scrollbar(master, **d)

    # ---- message-style dialogs ----

    _DIALOG_ICONS = {'info': '✓', 'warn': '⚠', 'error': '✕', 'question': '?'}
    _DIALOG_COLORS = {'info': 'success', 'warn': 'warn',
                      'error': 'danger', 'question': 'accent'}
    _BTN_TEXTS = {
        'zh': {'ok': '确定', 'yes': '是', 'no': '否', 'cancel': '取消',
               'retry': '重试'},
        'en': {'ok': 'OK', 'yes': 'Yes', 'no': 'No', 'cancel': 'Cancel',
               'retry': 'Retry'},
    }

    def _btn_text(self, key):
        lang = getattr(self._app, 'current_lang_name', 'en')
        return self._BTN_TEXTS.get(lang, self._BTN_TEXTS['en']).get(key, key)

    @staticmethod
    def _dialog_options(options):
        """解析原生 messagebox **options: parent / default / detail。

        其余未知键抛 TypeError (避免静默丢失参数)。
        """
        parent = options.pop('parent', None)
        default = options.pop('default', None)
        detail = options.pop('detail', '')
        if options:
            raise TypeError(
                'unsupported option(s): {}'.format(', '.join(sorted(options))))
        return parent, default, detail

    def _center_over_parent(self, dlg, parent):
        """居中 *dlg* 于 *parent* (装饰偏移补偿)；parent 为 None 时跳过。

        先按请求尺寸粗定位 (避免首帧闪烁), 显示后补偿 Windows 窗口
        管理器附加的装饰偏移 (标题栏/边框), 使内容区真正居中.
        注: 目标位置超出屏幕时会被窗口管理器钳制, 无法完全居中属正常.
        """
        if parent is None:
            return
        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        px = parent.winfo_rootx() + (parent.winfo_width() - dw) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - dh) // 2
        dlg.geometry(f'{dw}x{dh}+{px}+{py}')
        dlg.deiconify()
        dlg.update_idletasks()
        off_x = dlg.winfo_rootx() - px
        off_y = dlg.winfo_rooty() - py
        tx = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_width()) // 2 - off_x
        ty = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_height()) // 2 - off_y
        dlg.geometry(f'+{tx}+{ty}')

    def _dialog(self, parent, title, message, kind='info',
                buttons=('ok',), default=None, detail=''):
        """主题化模态对话框 — 居中于 *parent*, 返回被点击的按钮标识。

        *buttons*: 从左到右显示的按钮标识 (ok/yes/no/cancel/retry);
        *default*: 主按钮 (最右, Esc/关闭窗口等价于点击它), 缺省取末位。
        *detail*: message 下方的小字说明 (对应原生 detail 选项)。
        *parent* 为 None 时不 transient、不居中 (与原生行为一致)。
        """
        s = self._app.theme
        if default not in buttons:
            default = buttons[-1]
        icon = self._DIALOG_ICONS.get(kind, '•')
        color = s[self._DIALOG_COLORS.get(kind, 'fg')]

        dlg = self.Toplevel(parent)
        dlg.title(title)
        dlg.resizable(False, False)
        if parent is not None:
            dlg.transient(parent)
        dlg.configure(bg=s['card'])

        body = self.Frame(dlg, bg=s['card'])
        body.pack(padx=24, pady=(20, 12))
        self.Label(body, text=icon, font=self.font(30),
                   fg=color, bg=s['card']).pack(side=tk.LEFT, padx=(0, 12))
        text_col = self.Frame(body, bg=s['card'])
        text_col.pack(side=tk.LEFT, anchor='n')
        self.Label(text_col, text=message, font=self.font(10),
                   bg=s['card'], justify=tk.LEFT,
                   wraplength=320).pack(anchor='w')
        if detail:
            # 超长说明截断 — Label 无高度上限, 不截断会撑出屏幕
            if len(detail) > 1000:
                detail = detail[:1000] + '\n…(内容过长已截断)'
            self.Label(text_col, text=detail, font=self.font(8),
                       fg=s['hint'], bg=s['card'], justify=tk.LEFT,
                       wraplength=320).pack(anchor='w', pady=(6, 0))

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
                                  bg=s['sep'] if i != 0 else s['card'], fg=s['fg'],
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

        self._center_over_parent(dlg, parent)
        dlg.grab_set()
        dlg.focus_force()
        # 窗口显示后按钮才可取得焦点 (withdrawn 状态 focus_set 无效);
        # focus_force 在 Windows 上异步生效, 同栈内立即 focus_set 会被
        # 顶掉 (焦点回落到窗口本身) — after 延迟到映射完成后再设.
        # 实心(末位)按钮不持焦, 避免虚线焦点框; 仅描边 default 持焦
        if default_btn is not None and default != buttons[-1]:
            dlg.after(50, default_btn.focus_set)
        dlg.wait_window(dlg)
        return result.get('r', default)

    # 公开方法与原生 messagebox 签名一致: (title=None, message=None, **options).
    # options 支持 parent / default / detail (见 _dialog_options).

    def showinfo(self, title=None, message=None, **options):
        """Info dialog — same semantics as ``messagebox.showinfo``."""
        parent, default, detail = self._dialog_options(options)
        self._dialog(parent, title, message, kind='info', buttons=('ok',),
                     default=default, detail=detail)

    def showwarning(self, title=None, message=None, **options):
        """Warning dialog — same semantics as ``messagebox.showwarning``."""
        parent, default, detail = self._dialog_options(options)
        self._dialog(parent, title, message, kind='warn', buttons=('ok',),
                     default=default, detail=detail)

    # 历史别名 (迁移期兼容)
    showwarn = showwarning

    def showerror(self, title=None, message=None, **options):
        """Error dialog — same semantics as ``messagebox.showerror``."""
        parent, default, detail = self._dialog_options(options)
        self._dialog(parent, title, message, kind='error', buttons=('ok',),
                     default=default, detail=detail)

    def askyesno(self, title=None, message=None, **options):
        """Yes/No dialog — returns True for yes, False otherwise."""
        parent, default, detail = self._dialog_options(options)
        return self._dialog(parent, title, message, kind='question',
                            buttons=('no', 'yes'), default=default or 'no',
                            detail=detail) == 'yes'

    def askyesnocancel(self, title=None, message=None, **options):
        """Yes/No/Cancel dialog — returns True (yes) | False (no) | None (cancel).

        默认按钮为 cancel (Esc/关闭等价), 与原生 messagebox 一致.
        """
        parent, default, detail = self._dialog_options(options)
        r = self._dialog(parent, title, message, kind='question',
                         buttons=('cancel', 'no', 'yes'), default=default or 'cancel',
                         detail=detail)
        if r == 'cancel':
            return None
        return r == 'yes'

    def askquestion(self, title=None, message=None, **options):
        """Yes/No dialog — returns 'yes' or 'no' (default yes)."""
        parent, default, detail = self._dialog_options(options)
        return self._dialog(parent, title, message, kind='question',
                            buttons=('no', 'yes'), default=default or 'yes',
                            detail=detail)

    def askokcancel(self, title=None, message=None, **options):
        """OK/Cancel dialog — returns True for ok, False otherwise."""
        parent, default, detail = self._dialog_options(options)
        return self._dialog(parent, title, message, kind='question',
                            buttons=('cancel', 'ok'), default=default,
                            detail=detail) == 'ok'

    def askretrycancel(self, title=None, message=None, **options):
        """Retry/Cancel dialog — returns True for retry, False otherwise."""
        parent, default, detail = self._dialog_options(options)
        return self._dialog(parent, title, message, kind='question',
                            buttons=('cancel', 'retry'), default=default,
                            detail=detail) == 'retry'

    # ---- input dialogs (simpledialog 替代) ----

    _INPUT_ERRS = {
        'zh': {'int': '请输入整数', 'float': '请输入数字',
               'min': '不能小于 {}', 'max': '不能大于 {}'},
        'en': {'int': 'Please enter an integer', 'float': 'Please enter a number',
               'min': 'Must be >= {}', 'max': 'Must be <= {}'},
    }

    def _input_err(self, key, *args):
        lang = getattr(self._app, 'current_lang_name', 'en')
        tpl = self._INPUT_ERRS.get(lang, self._INPUT_ERRS['en']).get(key, key)
        return tpl.format(*args) if args else tpl

    def _input_dialog(self, parent, title, prompt, initialvalue='',
                      validate=None):
        """主题化输入对话框 — 返回输入值, 取消返回 None。

        *validate(text)*: 返回 str 视为错误文案 (显示并保持窗口, 可重试);
        返回其他值视为校验结果 (None 表示直接取原文本)。
        *parent* 为 None 时不 transient、不居中 (与原生行为一致)。
        """
        s = self._app.theme
        dlg = self.Toplevel(parent)
        dlg.title(title)
        dlg.resizable(False, False)
        if parent is not None:
            dlg.transient(parent)
        dlg.configure(bg=s['card'])

        body = self.Frame(dlg, bg=s['card'])
        body.pack(padx=24, pady=(20, 12), fill=tk.X)
        self.Label(body, text=prompt, font=self.font(10),
                   bg=s['card'], justify=tk.LEFT,
                   wraplength=320).pack(anchor='w')
        var = tk.StringVar(value=str(initialvalue))
        entry = self.Entry(body, textvariable=var, font=self.font(10))
        entry.pack(fill=tk.X, pady=(10, 0))
        err_lbl = self.Label(body, text='', font=self.font(8, 'bold'),
                             fg=s['danger'], bg=s['card'], justify=tk.LEFT)

        # 按钮栏: 与 _dialog 同款 (末位 ok 实心主按钮)
        btn_frame = self.Frame(dlg, bg=s['card'])
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X)

        result = {}

        def finish(r):
            # 防重入: 按钮 command 与窗口级 <Return> bind 可能同时触发
            # (焦点在按钮上时), 二次 destroy 会抛 TclError
            if result.get('r') is None:
                result['r'] = r
                dlg.destroy()

        def on_ok():
            if result.get('r') is not None:
                return
            text = var.get().strip()
            if validate is not None:
                res = validate(text)
                if isinstance(res, str):
                    err_lbl.config(text=res)
                    err_lbl.pack(anchor='w', pady=(8, 0))
                    return
                result['v'] = text if res is None else res
            else:
                result['v'] = text
            finish('ok')

        for i, b in enumerate(('cancel', 'ok')):
            if b == 'ok':
                btn = self.Button(btn_frame, text=self._btn_text(b),
                                  command=on_ok, bg=s['accent'],
                                  fg=s['accent_fg'], font=self.font(9, 'bold'))
            else:
                btn = self.Button(btn_frame, text=self._btn_text(b),
                                  command=lambda: finish('cancel'),
                                  bg=s['card'], fg=s['fg'],
                                  highlightbackground=s['sep'],
                                  highlightthickness=1)
            padx = (8, 4) if i == 0 else (4, 8)
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=padx)

        dlg.protocol('WM_DELETE_WINDOW', lambda: finish('cancel'))
        dlg.bind('<Escape>', lambda e: finish('cancel'))
        dlg.bind('<Return>', lambda e: on_ok())

        self._center_over_parent(dlg, parent)
        dlg.grab_set()

        # 窗口映射完成后再设焦点 (同 _dialog: 立即 focus_set 可能被
        # withdrawn/映射时序顶掉), 并全选初始内容
        def _focus_entry():
            entry.focus_set()
            entry.select_range(0, tk.END)

        dlg.after(50, _focus_entry)
        dlg.wait_window(dlg)
        if result.get('r') != 'ok':
            return None
        return result.get('v')

    # 公开方法与原生 simpledialog 签名一致: (title, prompt, **kw).
    # kw 支持 parent / initialvalue / minvalue / maxvalue.

    @staticmethod
    def _input_options(kw):
        """解析原生 simpledialog **kw: parent / initialvalue / minvalue / maxvalue。

        其余未知键抛 TypeError (避免静默丢失参数)。
        """
        parent = kw.pop('parent', None)
        initialvalue = kw.pop('initialvalue', '')
        minvalue = kw.pop('minvalue', None)
        maxvalue = kw.pop('maxvalue', None)
        if kw:
            raise TypeError(
                'unsupported option(s): {}'.format(', '.join(sorted(kw))))
        return parent, initialvalue, minvalue, maxvalue

    def askstring(self, title, prompt, **kw):
        """String input dialog — returns str or None (cancel)."""
        parent, initialvalue, minvalue, maxvalue = self._input_options(kw)
        if minvalue is None and maxvalue is None:
            return self._input_dialog(parent, title, prompt, str(initialvalue))

        # min/max 校验按原生 StringValidator 语义: 字符串比较
        # (validate 约定: 返回 str 为错误文案, None 表示取原文本)
        def _v(text):
            if minvalue is not None and text < minvalue:
                return self._input_err('min', minvalue)
            if maxvalue is not None and text > maxvalue:
                return self._input_err('max', maxvalue)
            return None

        return self._input_dialog(parent, title, prompt, str(initialvalue), _v)

    def askinteger(self, title, prompt, **kw):
        """Integer input dialog — returns int or None (cancel)."""
        parent, initialvalue, minvalue, maxvalue = self._input_options(kw)

        def _v(text):
            try:
                n = int(text)
            except ValueError:
                return self._input_err('int')
            if minvalue is not None and n < minvalue:
                return self._input_err('min', minvalue)
            if maxvalue is not None and n > maxvalue:
                return self._input_err('max', maxvalue)
            return n

        return self._input_dialog(parent, title, prompt, str(initialvalue), _v)

    def askfloat(self, title, prompt, **kw):
        """Float input dialog — returns float or None (cancel)."""
        parent, initialvalue, minvalue, maxvalue = self._input_options(kw)

        def _v(text):
            try:
                n = float(text)
            except ValueError:
                return self._input_err('float')
            if minvalue is not None and n < minvalue:
                return self._input_err('min', minvalue)
            if maxvalue is not None and n > maxvalue:
                return self._input_err('max', maxvalue)
            return n

        return self._input_dialog(parent, title, prompt, str(initialvalue), _v)

    # ---- scrollable containers ----

    def ScrollableText(self, master=None, cnf={}, **kwargs):
        """Text with built-in themed scrollbars (auto-hiding by default).

        Content changes (insert/delete) and layout changes auto-update the
        scrollbar visibility — no attach/polling needed. Pack the returned
        Text as usual; the scrollbars are laid out automatically.

        *scrollbars*: 'y' (vertical only, default), 'x', or 'both'.
        *auto_hide*=False: 滚动条常驻 (无 pack 抖动)
        yscrollcommand/xscrollcommand 由组件管理, 调用方传入会被覆盖.
        """
        scrollbars = kwargs.pop('scrollbars', 'y')
        auto_hide = kwargs.pop('auto_hide', True)
        d = self._defaults('Text', kwargs, cnf)
        # 默认等宽字体 (主题 Text.font 优先; 阶段 3 统一为 mono_font 入口时再调整)
        d.setdefault('font', ('Consolas', 9))
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

    def MarkdownText(self, master=None, cnf={}, **kwargs):
        """Text with built-in scrollbars + segment-level Markdown rendering.

        ScrollableText 的增强: append_markdown/flush/reset/apply_theme
        """
        theme_name = kwargs.pop('theme_name', self._app.current_theme_name)
        lang_name = kwargs.pop('lang_name', self._app.current_lang_name)
        scrollbars = kwargs.pop('scrollbars', 'y')
        auto_hide = kwargs.pop('auto_hide', True)
        d = self._defaults('Text', kwargs, cnf)
        d.setdefault('font', ('Consolas', 9))
        sb_y = (self.Scrollbar(master, auto_hide=auto_hide)
                if scrollbars in ('y', 'both') else None)
        sb_x = (self.Scrollbar(master, orient=tk.HORIZONTAL,
                               auto_hide=auto_hide)
                if scrollbars in ('x', 'both') else None)
        txt = MarkdownText(master, sb_y, sb_x, theme_name=theme_name, lang_name=lang_name, **d)
        if sb_y is not None:
            txt.configure(yscrollcommand=sb_y.set)
            sb_y.config(command=txt.yview)
        if sb_x is not None:
            txt.configure(xscrollcommand=sb_x.set)
            sb_x.config(command=txt.xview)
        return txt

    def ScrollableCanvas(self, master=None, cnf={}, **kwargs):
        """Canvas with built-in themed scrollbars (auto-hiding by default).

        Content lives in the returned canvas's ``inner`` Frame; its
        <Configure> drives scrollregion + scrollbar visibility — no
        attach/polling needed. Pack the returned Canvas as usual.

        *scrollbars*: 'y' (vertical only, default), 'x', or 'both'.
        *auto_hide*=False: 滚动条常驻 (无 pack 抖动)
        yscrollcommand/xscrollcommand 由组件管理, 调用方传入会被覆盖.
        """
        scrollbars = kwargs.pop('scrollbars', 'y')
        auto_hide = kwargs.pop('auto_hide', True)
        d = dict(self._app.theme.get('Frame', {}))
        d.setdefault('highlightthickness', 0)
        d.setdefault('borderwidth', 0)
        if cnf:
            d.update(cnf)
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

    def ScrollableListbox(self, master=None, cnf={}, **kwargs):
        """Listbox with a built-in auto-hiding themed vertical scrollbar.

        Content changes (insert/delete) and layout changes auto-update the
        scrollbar visibility — no attach/polling needed. Pack the returned
        Listbox as usual; the scrollbar is laid out automatically.
        yscrollcommand 由组件管理, 调用方传入会被覆盖.
        """
        d = self._defaults('Listbox', kwargs, cnf)
        sb = self.Scrollbar(master)
        lb = ScrollableListbox(master, sb, **d)
        lb.configure(yscrollcommand=sb.set)
        sb.config(command=lb.yview)
        return lb
