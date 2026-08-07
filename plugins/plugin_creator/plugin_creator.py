# -*- coding: utf-8 -*-
"""Plugin Creator — generate a new plugin package from a form."""
import os
import re
import sys
import tkinter as tk
from plugins.plugin import GuiPlugin

if sys.platform == 'win32':
    FONT_FAMILY = 'Microsoft YaHei'
elif sys.platform == 'darwin':
    FONT_FAMILY = 'PingFang SC'
else:
    FONT_FAMILY = 'Ubuntu'

_STYLE = {
    'dark': {
        'bg':        '#2b2b2b',
        'bar':       '#333333',
        'fg':        '#e0e0e0',
        'hint':      '#888888',
        'input_bg':  '#363636',
        'accent':    '#2d5a8a',
        'accent_fg': '#ffffff',
        'separator': '#3c3c3c',
        'dlg_bg':    '#555555',
    },
    'light': {
        'bg':        '#f5f6fa',
        'bar':       '#e8ecf1',
        'fg':        '#333333',
        'hint':      '#999999',
        'input_bg':  '#eaeaea',
        'accent':    '#4a90d9',
        'accent_fg': '#ffffff',
        'separator': '#d0d0d0',
        'dlg_bg':    '#ffffff',
    },
}

_LANG = {
    'zh': {
        'title':           '插件创建器',
        'package_name':    '包名/文件名',
        'class_name':      '类名',
        'display_name':    '显示名称 (name)',
        'name_zh':         '中文名称 (name_zh)',
        'name_en':         '英文名称 (name_en)',
        'namespace':       '命名空间 (namespace)',
        'priority':        '优先级 (priority)',
        'lifecycle':       '生命周期',
        'reload_label':    '关闭时销毁/每次重新创建 (reload)',
        'fixed_position':  '固定窗口位置 (fixed_position)',
        'fixed_size':      '固定窗口大小 (fixed_size)',
        'use_app_icon':    '是否使用软件图标 (use_app_icon)',
        'auto_start':      '是否跟随软件自启 (auto_start)',
        'start_hidden':    '自动启动时隐藏 (start_hidden)',
        'create_btn':      '创建插件',
        'required':        '请填写必填项：包名、类名、显示名称',
        'exists':          '插件目录已存在：\n{}\n请更换包名后重试。',
        'success':         '插件模板创建成功！\n\n目录: {}\n类名: {}\n\n请重新打开插件菜单查看。',
        'invalid_priority':'优先级必须为 0-100 之间的整数。',
        'invalid_pkg':     '包名必须是合法的 Python 标识符',
        'invalid_cls':     '类名必须为大驼峰命名 (PascalCase), 首字母大写',
        'err_title':       '创建失败',
        'ok_title':        '创建成功',
        'priority_hint':   '数值越大排序越靠前，范围 0-100',
        'plugin_type':     '插件类型',
        'type_gui':        'GUI 插件 (GuiPlugin)',
        'type_service':    '服务插件 (ServicePlugin)',
        'win_size':        '窗口大小',
        'width':           '宽度',
        'height':          '高度',
        'win_pos':         '窗口位置',
        'x':               'X',
        'y':               'Y',
    },
    'en': {
        'title':           'Plugin Creator',
        'package_name':    'Package Name / File Name',
        'class_name':      'Class Name',
        'display_name':    'Display Name (name)',
        'name_zh':         'Chinese Name (name_zh)',
        'name_en':         'English Name (name_en)',
        'namespace':       'Namespace',
        'priority':        'Priority',
        'lifecycle':       'Lifecycle',
        'reload_label':    'Destroy on close / Recreate each time (reload)',
        'fixed_position':  'fixed window position (fixed_position)',
        'fixed_size':      'fixed window size (fixed_size)',
        'use_app_icon':    'Use app icon (use_app_icon)',
        'auto_start':      'Auto-start with app (auto_start)',
        'start_hidden':    'hidden on auto-start (start_hidden)',
        'create_btn':      'Create Plugin',
        'required':        'Please fill required fields: Package Name, Class Name, Display Name',
        'exists':          'Plugin directory already exists:\n{}\nPlease change the package name.',
        'success':         'Plugin template created!\n\nDirectory: {}\nClass: {}\n\nRe-open the Plugins menu to see it.',
        'invalid_priority':'Priority must be an integer between 0-100.',
        'invalid_pkg':     'Package name must be a valid Python identifier',
        'invalid_cls':     'Class name must be PascalCase (start with uppercase letter)',
        'err_title':       'Create Failed',
        'ok_title':        'Create Succeeded',
        'priority_hint':   'Higher = shown first. Range 0-100',
        'plugin_type':     'Plugin Type',
        'type_gui':        'GUI Plugin (GuiPlugin)',
        'type_service':    'Service Plugin (ServicePlugin)',
        'win_size':        'Window Size',
        'width':           'Width',
        'height':          'Height',
        'win_pos':         'Window Position',
        'x':               'X',
        'y':               'Y',
    },
}

_GUI_TEMPLATE = '''# -*- coding: utf-8 -*-
"""{name} plugin."""
import tkinter as tk
from plugins.plugin import GuiPlugin


class {class_name}(GuiPlugin):
    name = "{name}"
    name_zh = "{name_zh}"
    name_en = "{name_en}"
    namespace = "{namespace}"
    priority = {priority}
    reload = {reload}
    fixed_position = {fixed_position}
    fixed_size = {fixed_size}
    use_app_icon = {use_app_icon}
    auto_start = {auto_start}
    start_hidden = {start_hidden}

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.title(self.name)
        self.geometry("{geometry_str}")
{resizable_line}
        # TODO: Build your UI here
        tk.Label(
            self, text="Hello from {name}!",
            font=("{font_family}", 12),
        ).pack(expand=True)
'''

_SERVICE_TEMPLATE = '''# -*- coding: utf-8 -*-
"""{name} service plugin."""
from plugins.plugin import ServicePlugin


class {class_name}(ServicePlugin):
    name = "{name}"
    name_zh = "{name_zh}"
    name_en = "{name_en}"
    namespace = "{namespace}"
    priority = {priority}
    auto_start = {auto_start}

    def __init__(self, app):
        super().__init__(app)
        # TODO: Register your services here via self.services.register(...)

    def on_start(self):
        """Called when the service starts."""
        pass

    def on_stop(self):
        """Called when the service stops."""
        pass
'''


class PluginCreator(GuiPlugin):
    name = "Plugin Creator"
    name_zh = "插件创建器"
    name_en = "Plugin Creator"
    namespace = "plugin_creator"
    priority = 999
    reload = True
    fixed_position = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)

        # Resolve theme & language via app proxy
        lang_name = self.app.current_lang_name
        theme_name = self.app.current_theme_name
        self._s = _STYLE.get(theme_name, _STYLE['dark'])
        self._l = _LANG[lang_name]
        s = self._s
        l = self._l

        self.title(l['title'])
        self.geometry('440x640')
        self.resizable(True, True)
        self.configure(bg=s['bg'])

        # ---- header ----
        header = tk.Frame(self, bg=s['bar'], height=32)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        tk.Label(header, text=f"  {l['title']}", bg=s['bar'], fg=s['fg'],
                 font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT, pady=4)

        self._status = tk.Label(header, text="", bg=s['bar'],
                                fg=s['hint'], font=("Consolas", 8))
        self._status.pack(side=tk.RIGHT, padx=8, pady=4)

        # ---- form body (scrollable via mousewheel + scrollbar) ----
        body = tk.Frame(self, bg=s['bg'])
        body.pack(fill=tk.BOTH, expand=True)
        canvas = self.components.ScrollableCanvas(body, bg=s['bg'], scrollbars='y')
        self._form = canvas.inner
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0), pady=(4, 0))

        # ---- field: package name ----
        self._pkg_var = tk.StringVar()
        self._pkg_var.trace('w', lambda *_: self._on_pkg_change())
        self._add_field(l['package_name'], self._pkg_var, required=True)
        tk.Label(self._form, text=l['invalid_pkg'], bg=s['bg'], fg=s['hint'],
                 font=(FONT_FAMILY, 8), anchor=tk.W).pack(
            fill=tk.X, padx=12, pady=(1, 0))

        # ---- field: class name ----
        self._cls_var = tk.StringVar()
        self._add_field(l['class_name'], self._cls_var, required=True)
        tk.Label(self._form, text=l['invalid_cls'], bg=s['bg'], fg=s['hint'],
                 font=(FONT_FAMILY, 8), anchor=tk.W).pack(
            fill=tk.X, padx=12, pady=(1, 0))

        # ---- field: display name ----
        self._name_var = tk.StringVar()
        self._add_field(l['display_name'], self._name_var, required=True)

        # ---- field: chinese name ----
        self._name_zh_var = tk.StringVar()
        self._add_field(l['name_zh'], self._name_zh_var)

        # ---- field: english name ----
        self._name_en_var = tk.StringVar()
        self._add_field(l['name_en'], self._name_en_var)

        # ---- field: namespace ----
        self._ns_var = tk.StringVar()
        self._add_field(l['namespace'], self._ns_var)

        # ---- field: priority ----
        self._prio_var = tk.StringVar(value="0")
        self._add_field(l['priority'], self._prio_var)
        tk.Label(self._form, text=l['priority_hint'], bg=s['bg'], fg=s['hint'],
                 font=(FONT_FAMILY, 8), anchor=tk.W).pack(
            fill=tk.X, padx=12, pady=(1, 0))

        # ---- plugin type selector ----
        tk.Label(self._form, text=l['plugin_type'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 10, "bold"), anchor=tk.W).pack(
            fill=tk.X, padx=12, pady=(10, 2))

        self._type_var = tk.StringVar(value='gui')
        type_frame = tk.Frame(self._form, bg=s['bg'])
        type_frame.pack(fill=tk.X, padx=12, pady=(0, 4))

        for val, label_key in [('service', 'type_service'), ('gui', 'type_gui')]:
            tk.Radiobutton(
                type_frame, text=l[label_key], variable=self._type_var,
                value=val, command=self._on_type_change,
                bg=s['bg'], fg=s['fg'],
                font=(FONT_FAMILY, 9),
                selectcolor=s['input_bg'],
                relief=tk.FLAT,
                activebackground=s['bg'],
                activeforeground=s['fg'],
                anchor=tk.W,
            ).pack(side=tk.RIGHT, padx=(12, 0))

        self._INDENT = 20  # left indent for expanded sub-fields

        self._bool_vars = {}
        self._bool_widgets = {}

        # ---- window size: label + fixed_size checkbox ----
        self._size_sep = tk.Frame(self._form, bg=s['separator'], height=1)
        self._size_sep.pack(fill=tk.X, padx=12, pady=(14, 6))

        self._size_header = tk.Frame(self._form, bg=s['bg'])
        self._size_header.pack(fill=tk.X, padx=12, pady=(0, 2))

        tk.Label(self._size_header, text=l['win_size'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT)

        self._fixed_size_var = tk.BooleanVar(value=False)
        self._bool_vars['fixed_size'] = self._fixed_size_var
        tk.Checkbutton(
            self._size_header, text=l['fixed_size'], variable=self._fixed_size_var,
            command=self._on_fixed_size_change,
            bg=s['bg'], fg=s['fg'],
            font=(FONT_FAMILY, 8),
            selectcolor=s['input_bg'],
            relief=tk.FLAT,
            activebackground=s['bg'],
            activeforeground=s['fg'],
        ).pack(side=tk.RIGHT)

        # size fields (expand with indent when fixed_size unchecked)
        self._size_fields = tk.Frame(self._form, bg=s['bg'])
        self._size_inner = tk.Frame(self._size_fields, bg=s['bg'])
        self._size_inner.pack(side=tk.RIGHT)
        tk.Label(self._size_inner, text=l['width'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._win_w_var = tk.StringVar(value="400")
        tk.Entry(self._size_inner, textvariable=self._win_w_var, width=6,
                 bg=s['input_bg'], fg=s['fg'], insertbackground=s['fg'],
                 font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                 highlightthickness=1,
                 highlightbackground=s['separator']).pack(
            side=tk.LEFT, padx=(0, 12), ipady=3)
        tk.Label(self._size_inner, text=l['height'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._win_h_var = tk.StringVar(value="300")
        tk.Entry(self._size_inner, textvariable=self._win_h_var, width=6,
                 bg=s['input_bg'], fg=s['fg'], insertbackground=s['fg'],
                 font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                 highlightthickness=1,
                 highlightbackground=s['separator']).pack(
            side=tk.LEFT, ipady=3)
        # ---- window position: label + fixed_position checkbox ----
        self._pos_sep = tk.Frame(self._form, bg=s['separator'], height=1)
        self._pos_sep.pack(fill=tk.X, padx=12, pady=(14, 6))

        self._pos_header = tk.Frame(self._form, bg=s['bg'])
        self._pos_header.pack(fill=tk.X, padx=12, pady=(0, 2))

        tk.Label(self._pos_header, text=l['win_pos'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT)

        self._fixed_pos_var = tk.BooleanVar(value=True)
        self._bool_vars['fixed_position'] = self._fixed_pos_var
        tk.Checkbutton(
            self._pos_header, text=l['fixed_position'], variable=self._fixed_pos_var,
            command=self._on_fixed_pos_change,
            bg=s['bg'], fg=s['fg'],
            font=(FONT_FAMILY, 8),
            selectcolor=s['input_bg'],
            relief=tk.FLAT,
            activebackground=s['bg'],
            activeforeground=s['fg'],
        ).pack(side=tk.RIGHT)

        # position fields (expand with indent when fixed_position unchecked)
        self._pos_fields = tk.Frame(self._form, bg=s['bg'])
        self._pos_inner = tk.Frame(self._pos_fields, bg=s['bg'])
        self._pos_inner.pack(side=tk.RIGHT)
        tk.Label(self._pos_inner, text=l['x'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._pos_x_var = tk.StringVar(value="100")
        tk.Entry(self._pos_inner, textvariable=self._pos_x_var, width=6,
                 bg=s['input_bg'], fg=s['fg'], insertbackground=s['fg'],
                 font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                 highlightthickness=1,
                 highlightbackground=s['separator']).pack(
            side=tk.LEFT, padx=(0, 12), ipady=3)
        tk.Label(self._pos_inner, text=l['y'], bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._pos_y_var = tk.StringVar(value="100")
        tk.Entry(self._pos_inner, textvariable=self._pos_y_var, width=6,
                 bg=s['input_bg'], fg=s['fg'], insertbackground=s['fg'],
                 font=(FONT_FAMILY, 10), relief=tk.FLAT, bd=0,
                 highlightthickness=1,
                 highlightbackground=s['separator']).pack(
            side=tk.LEFT, ipady=3)
        # ---- auto-start: standalone section ----
        self._autostart_sep = tk.Frame(self._form, bg=s['separator'], height=1)
        self._autostart_sep.pack(fill=tk.X, padx=12, pady=(14, 6))

        self._autostart_header = tk.Frame(self._form, bg=s['bg'])
        self._autostart_header.pack(fill=tk.X, padx=12, pady=(0, 2))

        tk.Label(self._autostart_header, text=l['auto_start'], bg=s['bg'],
                 fg=s['fg'], font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT)

        self._auto_start_var = tk.BooleanVar(value=False)
        self._bool_vars['auto_start'] = self._auto_start_var
        tk.Checkbutton(
            self._autostart_header, variable=self._auto_start_var,
            command=self._on_auto_start_change,
            bg=s['bg'], fg=s['fg'],
            font=(FONT_FAMILY, 8),
            selectcolor=s['input_bg'],
            relief=tk.FLAT,
            activebackground=s['bg'],
            activeforeground=s['fg'],
        ).pack(side=tk.RIGHT)

        # start_hidden — indented, shown when auto_start is checked
        self._start_hidden_var = tk.BooleanVar(value=False)
        self._bool_vars['start_hidden'] = self._start_hidden_var
        self._start_hidden_frame = tk.Frame(self._form, bg=s['bg'])
        self._start_hidden_cb = tk.Checkbutton(
            self._start_hidden_frame, text=l['start_hidden'],
            variable=self._start_hidden_var,
            bg=s['bg'], fg=s['fg'],
            font=(FONT_FAMILY, 8),
            selectcolor=s['input_bg'],
            relief=tk.FLAT,
            activebackground=s['bg'],
            activeforeground=s['fg'],
            anchor=tk.W,
        )
        self._start_hidden_cb.pack(side=tk.RIGHT)

        # ---- lifecycle: standalone section ----
        self._lifecycle_sep = tk.Frame(self._form, bg=s['separator'], height=1)
        self._lifecycle_sep.pack(fill=tk.X, padx=12, pady=(14, 6))

        self._lifecycle_header = tk.Frame(self._form, bg=s['bg'])
        self._lifecycle_header.pack(fill=tk.X, padx=12, pady=(0, 2))

        tk.Label(self._lifecycle_header, text=l['lifecycle'], bg=s['bg'],
                 fg=s['fg'], font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT)

        self._reload_var = tk.BooleanVar(value=True)
        self._bool_vars['reload'] = self._reload_var
        tk.Checkbutton(
            self._lifecycle_header, text=l['reload_label'],
            variable=self._reload_var,
            bg=s['bg'], fg=s['fg'],
            font=(FONT_FAMILY, 8),
            selectcolor=s['input_bg'],
            relief=tk.FLAT,
            activebackground=s['bg'],
            activeforeground=s['fg'],
        ).pack(side=tk.RIGHT)

        # ---- use_app_icon: label + checkbox (like auto-start) ----
        self._useapp_sep = tk.Frame(self._form, bg=s['separator'], height=1)
        self._useapp_sep.pack(fill=tk.X, padx=12, pady=(14, 6))

        self._useapp_header = tk.Frame(self._form, bg=s['bg'])
        self._useapp_header.pack(fill=tk.X, padx=12, pady=(0, 2))

        tk.Label(self._useapp_header, text=l['use_app_icon'], bg=s['bg'],
                 fg=s['fg'], font=(FONT_FAMILY, 10, "bold")).pack(side=tk.LEFT)

        self._use_app_icon_var = tk.BooleanVar(value=True)
        self._bool_vars['use_app_icon'] = self._use_app_icon_var
        tk.Checkbutton(
            self._useapp_header, variable=self._use_app_icon_var,
            bg=s['bg'], fg=s['fg'],
            font=(FONT_FAMILY, 8),
            selectcolor=s['input_bg'],
            relief=tk.FLAT,
            activebackground=s['bg'],
            activeforeground=s['fg'],
        ).pack(side=tk.RIGHT)

        # ---- create button ----
        self._btn_frame = tk.Frame(self, bg=s['bg'])
        self._btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=12, pady=(12, 12))

        self._create_btn = tk.Button(
            self._btn_frame, text=l['create_btn'],
            command=self._on_create,
            bg=s['accent'], fg=s['accent_fg'],
            font=(FONT_FAMILY, 10, "bold"),
            relief=tk.FLAT, padx=20, pady=6,
            cursor='hand2', bd=0,
            activebackground='#3a6fa8',
            activeforeground='#ffffff',
        )
        self._create_btn.pack(fill=tk.X)

        self._on_fixed_size_change()
        self._on_fixed_pos_change()
        self._on_auto_start_change()

        self.app.emit('app@window:set-geometry', self, w=440, h=640)

    def _add_field(self, label, var, required=False):
        s = self._s
        display = label + (" *" if required else "")
        tk.Label(self._form, text=display, bg=s['bg'], fg=s['fg'],
                 font=(FONT_FAMILY, 10), anchor=tk.W).pack(
            fill=tk.X, padx=12, pady=(8, 0))
        entry = tk.Entry(self._form, textvariable=var,
                         bg=s['input_bg'], fg=s['fg'],
                         insertbackground=s['fg'],
                         font=(FONT_FAMILY, 10),
                         relief=tk.FLAT, bd=0,
                         highlightthickness=1,
                         highlightbackground=s['separator'])
        entry.pack(fill=tk.X, padx=12, pady=(2, 0), ipady=4)

    def _on_pkg_change(self):
        """Auto-derive class name from package name (snake_case → PascalCase)."""
        pkg = self._pkg_var.get().strip()
        if pkg and not self._cls_var.get():
            # Convert snake_case to PascalCase
            parts = pkg.replace('-', '_').split('_')
            self._cls_var.set(''.join(p.capitalize() for p in parts if p))
            # Default namespace to the package name
            if not self._ns_var.get():
                self._ns_var.set(pkg)

    def _on_type_change(self):
        """Show/hide GUI-only checkboxes based on plugin type."""
        is_gui = self._type_var.get() == 'gui'
        for key, (var, cb, is_gui_only) in self._bool_widgets.items():
            if is_gui_only:
                if is_gui:
                    cb.grid()
                else:
                    cb.grid_remove()
        # Service has no GUI sections
        self._update_sections_visibility()

    def _on_fixed_size_change(self):
        self._update_sections_visibility()

    def _on_fixed_pos_change(self):
        self._update_sections_visibility()

    def _on_auto_start_change(self):
        """Show/hide start_hidden based on auto_start checkbox."""
        self._update_sections_visibility()
        if not self._auto_start_var.get():
            self._start_hidden_var.set(False)

    def _update_sections_visibility(self):
        """Rebuild the form — forget all, then repack visible sections in order."""
        is_gui = self._type_var.get() == 'gui'

        # 1. Forget every dynamic widget first
        for w in (self._size_sep, self._size_header, self._size_fields,
                  self._pos_sep, self._pos_header, self._pos_fields,
                  self._lifecycle_sep, self._lifecycle_header,
                  self._autostart_sep, self._autostart_header,
                  self._start_hidden_frame,
                  self._useapp_sep, self._useapp_header):
            try:
                w.pack_forget()
            except Exception:
                pass

        if not is_gui:
            # Service: only auto-start section
            self._autostart_sep.pack(fill=tk.X, padx=12, pady=(14, 6))
            self._autostart_header.pack(fill=tk.X, padx=12, pady=(0, 2))
            return

        # GUI: repack visible sections in vertical order
        # -- window size --
        self._size_sep.pack(fill=tk.X, padx=12, pady=(14, 6))
        self._size_header.pack(fill=tk.X, padx=12, pady=(0, 2))
        if not self._fixed_size_var.get():
            self._size_fields.pack(fill=tk.X, padx=12, pady=(0, 6))

        # -- window position --
        self._pos_sep.pack(fill=tk.X, padx=12, pady=(14, 6))
        self._pos_header.pack(fill=tk.X, padx=12, pady=(0, 2))
        if not self._fixed_pos_var.get():
            self._pos_fields.pack(fill=tk.X, padx=12, pady=(0, 6))

        # -- lifecycle --
        self._lifecycle_sep.pack(fill=tk.X, padx=12, pady=(14, 6))
        self._lifecycle_header.pack(fill=tk.X, padx=12, pady=(0, 2))

        # -- auto-start --
        self._autostart_sep.pack(fill=tk.X, padx=12, pady=(14, 6))
        self._autostart_header.pack(fill=tk.X, padx=12, pady=(0, 2))
        if self._auto_start_var.get():
            self._start_hidden_frame.pack(
                fill=tk.X, padx=12, pady=(0, 4))

        # -- use_app_icon --
        self._useapp_sep.pack(fill=tk.X, padx=12, pady=(14, 6))
        self._useapp_header.pack(fill=tk.X, padx=12, pady=(0, 2))

    def _on_create(self):
        l = self._l

        # Validate required fields
        pkg = self._pkg_var.get().strip()
        cls = self._cls_var.get().strip()
        name = self._name_var.get().strip()

        if not pkg or not cls or not name:
            self._show_dialog('warn', l['err_title'], l['required'])
            return

        # Validate package name: must be a valid Python identifier
        if not pkg.isidentifier():
            self._show_dialog('warn', l['err_title'], l['invalid_pkg'])
            return

        # Validate class name: PascalCase
        if not re.match(r'^[A-Z][a-zA-Z0-9_]*$', cls):
            self._show_dialog('warn', l['err_title'], l['invalid_cls'])
            return

        # Validate priority
        prio_str = self._prio_var.get().strip()
        try:
            priority = int(prio_str) if prio_str else 0
        except ValueError:
            self._show_dialog('warn', l['err_title'], l['invalid_priority'])
            return
        if not (0 <= priority <= 100):
            self._show_dialog('warn', l['err_title'], l['invalid_priority'])
            return

        # Resolve target directory
        target_dir = os.path.join(self.app.plugin_path, pkg)

        # Check if already exists
        if os.path.exists(target_dir):
            self._show_dialog('warn', l['err_title'], l['exists'].format(target_dir))
            return

        # Gather common values
        is_gui = self._type_var.get() == 'gui'
        name_zh = self._name_zh_var.get().strip()
        name_en = self._name_en_var.get().strip()
        namespace = self._ns_var.get().strip() or pkg
        auto_start = self._bool_vars['auto_start'].get()

        # Create package directory
        try:
            os.makedirs(target_dir)
        except OSError as e:
            self._show_dialog('error', l['err_title'], str(e))
            return

        # Write __init__.py
        init_path = os.path.join(target_dir, '__init__.py')
        with open(init_path, 'w', encoding='utf-8') as f:
            f.write(f'# -*- coding: utf-8 -*-\nfrom .{pkg} import {cls}\n')

        # Write module file
        module_path = os.path.join(target_dir, f'{pkg}.py')
        if is_gui:
            # Geometry string: "WxH" or "WxH+X+Y"
            win_w = self._win_w_var.get().strip() or "400"
            win_h = self._win_h_var.get().strip() or "300"
            fixed_pos_val = self._bool_vars['fixed_position'].get()
            if fixed_pos_val:
                geometry_str = f"{win_w}x{win_h}"
            else:
                pos_x = self._pos_x_var.get().strip() or "100"
                pos_y = self._pos_y_var.get().strip() or "100"
                geometry_str = f"{win_w}x{win_h}+{pos_x}+{pos_y}"

            fixed_size_val = self._bool_vars['fixed_size'].get()
            resizable_line = "" if fixed_size_val else (
                "        self.resizable(True, True)"
            )
            module_content = _GUI_TEMPLATE.format(
                name=name,
                name_zh=name_zh,
                name_en=name_en,
                class_name=cls,
                namespace=namespace,
                priority=priority,
                reload=self._bool_vars['reload'].get(),
                fixed_position=fixed_pos_val,
                fixed_size=fixed_size_val,
                use_app_icon=self._bool_vars['use_app_icon'].get(),
                auto_start=auto_start,
                start_hidden=self._bool_vars['start_hidden'].get(),
                geometry_str=geometry_str,
                resizable_line=resizable_line,
                font_family=FONT_FAMILY,
            )
        else:
            module_content = _SERVICE_TEMPLATE.format(
                name=name,
                name_zh=name_zh,
                name_en=name_en,
                class_name=cls,
                namespace=namespace,
                priority=priority,
                auto_start=auto_start,
            )
        with open(module_path, 'w', encoding='utf-8') as f:
            f.write(module_content)

        self._show_dialog('info', l['ok_title'],
                          l['success'].format(target_dir, cls))
        # self.destroy()

    def _show_dialog(self, kind, title, message):
        """Show a custom dialog centered on this plugin window."""
        dlg = tk.Toplevel(self)
        dlg.withdraw()  # hide until positioned to avoid top-left flash
        dlg.title(title)
        dlg.resizable(False, False)
        dlg.transient(self)
        s = self._s
        dbg = s['dlg_bg']
        dlg.configure(bg=dbg)
        # Set icon via app event
        self.app.emit('app@window:set-icon', dlg)
        # icons
        icons = {'info': '✓', 'warn': '⚠', 'error': '✕'}
        icon = icons.get(kind, '•')
        colors = {'info': '#4caf50', 'warn': '#ff9800', 'error': '#f44336'}
        color = colors.get(kind, s['fg'])
        icon_size = 40 if kind == 'info' else 32
        # Content
        body = tk.Frame(dlg, bg=dbg)
        body.pack(padx=24, pady=(20, 12))
        tk.Label(body, text=icon, font=("Segoe UI", icon_size), fg=color,
                 bg=dbg).pack(side=tk.LEFT, padx=(0, 12))
        tk.Label(body, text=message, font=(FONT_FAMILY, 10), fg=s['fg'],
                 bg=dbg, justify=tk.LEFT, wraplength=240).pack(side=tk.LEFT)
        # Button
        btn_frame = tk.Frame(dlg, bg=dbg)
        btn_frame.pack(pady=(0, 16))
        tk.Button(btn_frame, text="OK", command=dlg.destroy,
                  bg=s['accent'], fg=s['accent_fg'], relief=tk.FLAT,
                  font=(FONT_FAMILY, 10, "bold"), padx=24, pady=4,
                  cursor='hand2', bd=0,
                  activebackground='#3a6fa8',
                  activeforeground='#ffffff').pack()
        # Center on plugin window (use reqwidth/reqheight — winfo_width/height
        # return 1 while the window is withdrawn)
        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        px = self.winfo_rootx() + (self.winfo_width() - dw) // 2
        py = self.winfo_rooty() + (self.winfo_height() - dh) // 2
        dlg.geometry(f'{dw}x{dh}+{px}+{py}')
        dlg.deiconify()  # show at final position
        dlg.grab_set()
        dlg.focus_force()
        dlg.wait_window()

    def on_destroy(self):
        """Clean up any lingering mousewheel bindings."""
        try:
            self.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().on_destroy()
