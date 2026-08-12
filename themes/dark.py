# -*- coding: utf-8 -*-
"""Dark color theme.

结构约定：
- 小写键    = 基础语义色 (跨控件共享, UI/插件层显式覆盖用)
- PascalCase = 控件默认样式 (components 库取值来源; 调用方参数覆盖)

字体不在此处定义——由 common/components 统一补 (FONT_FAMILY, size)
"""
DARK_THEME = {
    # ---- 基础语义色 ----
    'bg': '#191a1b',
    'fg': '#bbbebf',
    'accent': '#297aa0',
    'accent_fg': '#ffffff',
    'hint': '#888888',
    'sep': '#4a4a4a',
    'border': '#2b2b2b',
    'card': '#2b2b2b',
    'bar': '#292a2b',
    'hover': '#292a2b',
    'success': '#4caf50',
    'warn': '#ff9800',
    'danger': '#d94a4a',
    'nav_bg': '#191a1b',
    'nav_hover_bg': '#292a2b',

    # ---- 控件默认样式 ----
    'Button': {
        'bg': '#297aa0',
        'fg': '#e0e0e0',
        'disabled_bg': '#333333',
        'activebackground': '#297aa0',
        'activeforeground': '#e0e0e0',
        'padx': 14,
        'pady': 4,
        'relief': 'flat',
        'cursor': 'hand2',
        'bd': 0,
        'highlightthickness': 0,
    },
    'Label': {
        'bg': '#191a1b',
        'fg': '#bbbebf',
        'padx': 4,
        'pady': 2,
    },
    'Entry': {
        'bg': '#121314',
        'fg': '#bbbebf',
        'insertbackground': '#bbbebf',
        'highlightbackground': '#57616b',
        'highlightthickness': 1,
        'relief': 'flat',
        'bd': 0,
    },
    'Spinbox': {
        'bg': '#3c3c3c',
        'fg': '#e0e0e0',
        'insertbackground': '#e0e0e0',
        'buttonbackground': '#333333',
        'highlightbackground': '#57616b',
        'highlightthickness': 1,
        'relief': 'flat',
        'bd': 1,
    },
    'Menubutton': {
        'bg': '#333333',
        'fg': '#e0e0e0',
        'activebackground': '#57616b',
        'activeforeground': '#ffffff',
        'relief': 'flat',
        'bd': 0,
        'cursor': 'hand2',
        'indicatoron': 0,
    },
    'Listbox': {
        'bg': '#121314',
        'fg': '#bbbebf',
        'selectbackground': '#297aa0',
        'selectforeground': '#ffffff',
        'relief': 'flat',
        'bd': 0,
        'highlightthickness': 0,
    },
    'Text': {
        'bg': '#121314',
        'fg': '#bbbebf',
        'insertbackground': '#bbbebf',
        'padx': 6,
        'pady': 6,
        'relief': 'flat',
        'bd': 0,
        'highlightthickness': 0,
    },
    'Checkbutton': {
        'bg': '#191a1b',
        'fg': '#bbbebf',
        'selectcolor': '#191a1b',
        'activebackground': '#191a1b',
        'activeforeground': '#bbbebf',
        'relief': 'flat',
        'padx': 4,
        'pady': 2,
    },
    'Radiobutton': {
        'bg': '#191a1b',
        'fg': '#bbbebf',
        'selectcolor': '#191a1b',
        'activebackground': '#191a1b',
        'activeforeground': '#bbbebf',
        'relief': 'flat',
        'padx': 4,
        'pady': 2,
    },
    'Frame': {
        'bg': '#191a1b',
    },
    'Toplevel': {
        'bg': '#191a1b',
    },
    'Menu': {
        'bg': '#292a2b',
        'fg': '#bbbebf',
        'activebackground': '#57616b',
        'activeforeground': '#ffffff',
        'relief': 'flat',
        'activeborderwidth': 3,
        'tearoff': 0,
    },
    'Scrollbar': {
        'bg': '#333333',
        'troughcolor': '#252525',
        'width': 12,
        'relief': 'flat',
        'borderwidth': 0,
    },
    'Separator': {
        'bg': '#4a4a4a',
        'height': 1,
    },
    'Card': {
        'bg': '#2b2b2b',
        'highlightthickness': 1,
        'highlightbackground': '#4a4a4a',
    },
    'Combobox': {
        'fieldbackground': '#121314',
        'background': '#121314',
        'foreground': '#bbbebf',
        'selectbackground': '#297aa0',
        'arrowcolor': '#bbbebf',
        # 边框: border=0 为无边框 (布局 -border), lightcolor/darkcolor
        # 控制边框颜色 (style borderwidth 对 Combobox 无效)
        'border': 0,
        'borderwidth': 1,
        'lightcolor': '#222222',
        'darkcolor': '#222222',
    },
}
