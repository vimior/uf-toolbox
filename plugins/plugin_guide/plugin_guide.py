# -*- coding: utf-8 -*-
"""Plugin development guide — loads and renders docs/plugin-guide.md."""
import os
import tkinter as tk
from plugins.plugin import GuiPlugin


class PluginGuide(GuiPlugin):
    name = "Plugin Guide"
    name_zh = "插件指南"
    name_en = "Plugin Guide"
    namespace = "plugin_guide"
    fixed_position = True
    fixed_size = False
    reload = True
    priority = 1000

    def __init__(self, parent=None, app=None, doc=None, title_zh=None, title_en=None):
        if title_zh:
            type(self).name_zh = title_zh
        if title_en:
            type(self).name_en = title_en
        self._doc_name = doc or 'plugin-guide.md'
        super().__init__(parent, app)
        lang_name = self.app.current_lang_name
        s = self.app.theme

        self.title(self.name_zh if lang_name == 'zh' else self.name_en)
        self.geometry("820x600")
        self.resizable(True, True)

        # ---- body ----
        # 文本区（card 色，与窗口背景分层），边距与日志窗口一致（顶 8 底 6）
        outer = self.components.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 6))

        self._txt = self.components.MarkdownText(
            outer, wrap=tk.WORD, font=self.components.mono_font(10),
            bg=s['card'], padx=18, tabs=("1.5c",),
            theme_name=self.app.current_theme_name, lang_name=lang_name,
            auto_hide=False)  # 文档总超出，滚动条常驻避免布局抖动
        self._txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 主题切换时刷新 markdown tag 颜色 (框架自动清理订阅)
        self.app.on('app@theme:changed', self._on_theme_changed)

        # ---- load & render ----
        # 滚轮由 ScrollableText 内置（Enter/Leave 全局绑定）
        # 静态整文档: append 全部 + flush 渲染末段残留
        self._txt.append_markdown(self._load_doc(lang_name))
        self._txt.flush()
        self._txt.configure(state=tk.DISABLED)

    def _on_theme_changed(self, _name=None):
        self._txt.apply_theme(self.app.current_theme_name)

    # ---- loader ----

    def _load_doc(self, lang):
        base = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        # Try language-specific doc first, fall back to generic
        doc_name = self._doc_name
        stem, ext = os.path.splitext(doc_name)
        for name in (f'{stem}-{lang}{ext}', doc_name):
            path = os.path.join(base, 'docs', name)
            if os.path.isfile(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
        return "# Error\n\nDocumentation not found."
