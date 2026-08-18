# -*- coding: utf-8 -*-
"""Theme-aware Toplevel base class."""
import tkinter as tk


class AppToplevel(tk.Toplevel):
    """主题感知 Toplevel — 构造时注入 app, 自动套主题默认样式.

    默认背景来自 ``app.theme['Toplevel']['bg']``, 调用方参数覆盖;
    ``app=None`` 时退化为裸 tk.Toplevel。

    防闪烁: 构造后立即 withdraw; 若构造时类属性 ``_hidden_launch`` 为
    False(默认) 则注册 after(0) 自动显示——调用方在同一调用栈内完成
    UI 构建与定位后窗口自动 deiconify, 不会在默认位置闪现.
    隐藏启动 (如插件 manager 的 hidden/start_hidden) 由调用方在构造前
    设置类属性 ``_hidden_launch = True``, 构造后恢复为 False;
    此时不注册 after, 窗口保持 withdrawn, 由调用方决定何时显示.

    窗口图标：构造时自动 emit ``window:set-icon`` (类属性
    ``use_app_icon`` 为 False 或 app 为 None 时跳过) ——调用方无需
    手动设置图标.
    """

    def __init__(self, master=None, cnf={}, app=None, **kwargs):
        self._app = app
        if app is not None:
            d = dict(app.theme.get('Toplevel', {}))
            d.update(cnf)      # cnf 位置参数（原生用法）
            d.update(kwargs)   # 调用方参数覆盖主题默认
            kwargs = d
        super().__init__(master, **kwargs)
        # self.geometry('+{}+{}'.format(-9999, -9999))
        self.withdraw()
        if self._app is not None and getattr(self, 'use_app_icon', True):
            self._app.emit('app@window:set-icon', self)
        if not getattr(self.__class__, '_hidden_launch', False):
            self._auto_show_job = self.after(0, self._auto_show)

    def _auto_show(self):
        try:
            if self.winfo_exists():
                self.deiconify()
        except tk.TclError:
            pass
