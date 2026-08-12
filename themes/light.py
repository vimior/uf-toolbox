# -*- coding: utf-8 -*-
"""Light color theme.

结构约定：
- 小写键    = 基础语义色 (跨控件共享, UI/插件层显式覆盖用)
- PascalCase = 控件默认样式 (components 库取值来源; 调用方参数覆盖)

字体不在此处定义——由 common/components 统一补 (FONT_FAMILY, size)
"""
LIGHT_THEME = {
    # ---- 基础语义色 ----
    'bg': '#f5f6fa',
    'fg': '#333333',
    'accent': '#4a90d9',
    'accent_fg': '#ffffff',
    'hint': '#999999',
    'sep': '#cccccc',
    'border': '#f5f6fa',
    'card': '#ffffff',
    'bar': '#e0e0e0',
    'hover': '#d0d0d0',
    'success': '#388e3c',
    'warn': '#f57c00',
    'danger': '#c0392b',
    'nav_bg': '#e8ecf1',
    'nav_hover_bg': '#bfbfbf',

    # ---- 控件默认样式 ----
    'Button': {
        'bg': '#3a7bc8',
        'fg': 'white',
        'disabled_bg': '#dcdcdc',
        'activebackground': '#3a7bc8',
        'activeforeground': 'white',
        'padx': 14,
        'pady': 4,
        'relief': 'flat',
        'cursor': 'hand2',
        'bd': 0,
        'highlightthickness': 0,
    },
    'Label': {
        'bg': '#f5f6fa',
        'fg': '#333333',
        'padx': 4,
        'pady': 2,
    },
    'Entry': {
        'bg': '#eaeaea',
        'fg': '#333333',
        'insertbackground': '#333333',
        'highlightbackground': '#57616b',
        'highlightthickness': 1,
        'relief': 'flat',
        'bd': 0,
    },
    'Spinbox': {
        'bg': '#ffffff',
        'fg': '#333333',
        'insertbackground': '#333333',
        'buttonbackground': '#e8ecf1',
        'highlightbackground': '#57616b',
        'highlightthickness': 1,
        'relief': 'flat',
        'bd': 1,
    },
    'Menubutton': {
        'bg': '#e8ecf1',
        'fg': '#333333',
        'activebackground': '#57616b',
        'activeforeground': '#ffffff',
        'relief': 'flat',
        'bd': 0,
        'cursor': 'hand2',
        'indicatoron': 0,
    },
    'Listbox': {
        'bg': '#ffffff',
        'fg': '#333333',
        'selectbackground': '#4a90d9',
        'selectforeground': '#ffffff',
        'relief': 'flat',
        'bd': 0,
        'highlightthickness': 0,
    },
    'Text': {
        'bg': '#ffffff',
        'fg': '#333333',
        'insertbackground': '#333333',
        'padx': 6,
        'pady': 6,
        'relief': 'flat',
        'bd': 0,
        'highlightthickness': 0,
    },
    'Checkbutton': {
        'bg': '#f5f6fa',
        'fg': '#333333',
        'selectcolor': '#f5f6fa',
        'activebackground': '#f5f6fa',
        'activeforeground': '#333333',
        'relief': 'flat',
        'padx': 4,
        'pady': 2,
    },
    'Radiobutton': {
        'bg': '#f5f6fa',
        'fg': '#333333',
        'selectcolor': '#f5f6fa',
        'activebackground': '#f5f6fa',
        'activeforeground': '#333333',
        'relief': 'flat',
        'padx': 4,
        'pady': 2,
    },
    'Frame': {
        'bg': '#f5f6fa',
    },
    'Toplevel': {
        'bg': '#f5f6fa',
    },
    'Menu': {
        'bg': '#ffffff',
        'fg': '#333333',
        'activebackground': '#57616b',
        'activeforeground': '#ffffff',
        'relief': 'flat',
        'activeborderwidth': 3,
        'tearoff': 0,
    },
    'Scrollbar': {
        'bg': '#e0e0e0',
        'troughcolor': '#f5f5f5',
        'width': 12,
        'relief': 'flat',
        'borderwidth': 0,
    },
    'Separator': {
        'bg': '#cccccc',
        'height': 1,
    },
    'Card': {
        'bg': '#ffffff',
        'highlightthickness': 1,
        'highlightbackground': '#cccccc',
    },
    'Combobox': {
        'fieldbackground': '#eaeaea',
        'background': '#eaeaea',
        'foreground': '#333333',
        'selectbackground': '#4a90d9',
        'arrowcolor': '#333333',
    },
}
