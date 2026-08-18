# -*- coding: utf-8 -*-
"""MarkdownText — 带 Markdown 渲染的文本组件 (ScrollableText 子类).

段级缓冲: append_markdown 累积文本, 完整段 (空行分隔且代码块闭合)
即时渲染; 末段保留到 flush() — 适配流式输出场景, 避免半成品块被
样式化后反复重绘。

支持语法: ``` 围栏代码块 (背景 + 尾随 [复制] 文本标签) / `行内代码` /
#~### 标题 / **粗体** / *斜体* / ~~删除线~~ / [链接](url) 可点击 /
- * 1. 列表 / > 引用 / --- 水平线 / | | 表格 (对齐文本) / 空行折叠。

复制功能用纯文本标签 + tag_bind 实现 (不用 window_create 嵌入按钮 —
嵌入 window 会捕获鼠标事件, 阻断代码块文本的拖选)。

用法:
    w = MarkdownText(master, colors=MD_COLORS['dark'])
    w.append_markdown(text, base_tag='assistant')   # 流式增量
    w.flush()        # 流结束时渲染残留
    w.reset()        # 清空缓冲/状态 (clear 时)
    w.apply_theme(theme_name)   # 主题切换时刷新 tag 颜色
"""
import re
import webbrowser
import tkinter as tk

from .scrollable_text import ScrollableText

# 默认主题色表 (light/dark) — 惯例参照 plugin_guide._DOC_COLORS
MD_COLORS = {
    'light': {
        'code_bg': '#f0f0f0', 'code_fg': '#a31515',
        'h1': '#1a1a1a', 'h2': '#333333',
        'btn_bg': '#e0e0e0',
        'link': '#0366d6', 'quote': '#666666',
        'quote_bg': '#f5f6fa',
        'table_bg': '#f8f8f8',
        'hr': '#999999', 'strike': '#888888',
    },
    'dark': {
        'code_bg': '#1a1a1a', 'code_fg': '#ce9178',
        'h1': '#e8e8e8', 'h2': '#cccccc',
        'btn_bg': '#333333',
        'link': '#58a6ff', 'quote': '#8a8f98',
        'quote_bg': '#232425',
        'table_bg': '#1e1f20',
        'hr': '#555555', 'strike': '#777777',
    },
}

_LANG = {
    'zh': {
        'copy': '复制',
    },
    'en': {
        'copy': 'Copy',
    },
}

# 行内语法 (顺序匹配): 粗斜体 → 粗体 → 下划线粗体 → 斜体 → 代码 →
# 删除线 → 链接 → 裸 URL
_INLINE_RE = re.compile(
    r'(\*\*\*(.+?)\*\*\*)'        # 2: 粗斜体
    r'|(\*\*(.+?)\*\*)'           # 4: 粗体
    r'|(__(\S.*?\S)__)'           # 6: 下划线粗体
    r'|(\*(.+?)\*)'               # 8: 斜体
    r'|(`(.+?)`)'                 # 10: 行内代码
    r'|(~~(.+?)~~)'               # 12: 删除线
    r'|(\[(.+?)\]\((.+?)\))'      # 14/15: 链接
    # 16: 裸 URL — 限定 ASCII 合法字符集, 中文句读/正文不会被吞进链接
    r'|(https?://[A-Za-z0-9\-._~:/?#@!$&\'*+,;=%\[\]]+)'
)

_TABLE_SEP = re.compile(r'^\|(\s*[\-:]+\s*\|)+$')
_TABLE_ROW = re.compile(r'^\|.*\|$')
# 水平线: --- / *** / ___ / * * * (整行同一符号 ≥3 个)
_HR = re.compile(r'^([-*_])( ?\1){2,}$')
_ORDERED = re.compile(r'^(\s*\d+\.\s+)(.+)')
_TASK = re.compile(r'^\s*[-*] \[( |x|X)\]\s+(.+)')

_MAX_CELL_W = 60   # 表格单元格最大显示宽度, 超出截断

# 转义字符 → 私有区占位 (不参与样式正则, 插入时还原)
_ESC_MAP = {'*': '', '_': '', '`': '', '\\': ''}
_ESC_RE = re.compile(r'\\([*_`\\])')


def _escape(s):
    return _ESC_RE.sub(lambda m: _ESC_MAP[m.group(1)], s)


def _unescape(s):
    for real, esc in _ESC_MAP.items():
        s = s.replace(esc, real)
    return s


def _disp_width(s):
    """显示宽度: 东亚字符按 2 计 (等宽字体下中文占两列)."""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(s))


_CELL_MD = re.compile(r'(\*\*(.+?)\*\*)|(\*(.+?)\*)|(`(.+?)`)')


def _clean_cell(s):
    """单元格内 markdown 标记清理 (**bold** / *italic* / `code` → 纯文本)."""
    return _CELL_MD.sub(lambda m: (m.group(2) or m.group(4) or m.group(6)
                                   or m.group(0)), s)


def _trunc_disp(s, w):
    """按显示宽度截断 (东亚字符宽 2)."""
    out, cur = '', 0
    for ch in str(s):
        cw = 2 if ord(ch) > 0x2E7F else 1
        if cur + cw > w:
            break
        out += ch
        cur += cw
    return out


def _fmt_row(cells, widths, aligns=None):
    """按显示宽度对齐; aligns 为每列 'l'/'c'/'r' (缺省左对齐).

    超长单元格按显示宽度截断 + '…', 保证表格不被撑破。
    """
    aligns = aligns or ['l'] * len(widths)
    parts = []
    for c, w, a in zip(cells, widths, aligns):
        c = _clean_cell(c)
        if _disp_width(c) > _MAX_CELL_W:
            c = _trunc_disp(c, _MAX_CELL_W) + '…'
        pad = max(0, w - _disp_width(c))
        if a == 'r':
            parts.append(' %s%s ' % (' ' * pad, c))
        elif a == 'c':
            left = pad // 2
            parts.append(' %s%s%s ' % (' ' * left, c, ' ' * (pad - left)))
        else:
            parts.append(' %s%s ' % (c, ' ' * pad))
    return '|' + '|'.join(parts) + '|'


class MarkdownText(ScrollableText):
    """ScrollableText + 段级 Markdown 渲染."""

    def __init__(self, master, sb_y=None, sb_x=None, theme_name=None, lang_name=None, **kwargs):
        super().__init__(master, sb_y, sb_x, **kwargs)
        self._md_buffer = ''
        self._md_in_code = False
        self._md_last_tag = None
        self._md_links = []    # 已创建的链接 tag 名 (apply_theme 刷新用)
        self._md_copies = 0    # 复制标签计数
        self._theme = MD_COLORS.get(theme_name or 'dark', MD_COLORS['dark'])
        self._lang = _LANG.get(lang_name or 'en', _LANG['en'])
        self.apply_theme(theme_name or 'dark')

        self.config(insertwidth=0)
        # 带背景的 tag 会盖住选中高亮 (Tk 已知行为) — 选中期间临时清背景
        self.bind('<<Selection>>', self._on_sel_change)

    # 带背景的 tag — Tk 中 tag 背景会盖住选中高亮, 选中期间临时清除
    _BG_TAGS = ('md_code', 'md_code_block', 'md_table',
                'md_quote', 'md_quote_2', 'md_quote_3')

    HR_WIDTH = 60   # 水平线长度 (字符数) — 子类/实例可覆盖

    def _on_sel_change(self, _event=None):
        """选中期间清除带背景 tag 的背景, 让选中高亮可见; 取消后恢复."""
        if self.tag_ranges('sel'):
            for tag in self._BG_TAGS:
                try:
                    self.tag_configure(tag, background='')
                except tk.TclError:
                    pass
        else:
            self.apply_theme()

    # ---- 公开 API ----

    def append_markdown(self, text, base_tag=None):
        """追加文本 — 完整段即时渲染, 末段 (可能不完整) 留缓冲."""
        self._md_last_tag = base_tag
        self._md_buffer += text
        self._render_stable()

    def flush(self):
        """渲染缓冲全部残留 (流结束/回显收尾时调用)."""
        if not self._md_buffer:
            return
        buf, self._md_buffer = self._md_buffer, ''
        self._with_editable(self._render_buf, buf)

    def reset(self):
        """清空缓冲与代码块状态 (clear/error 时调用)."""
        self._md_buffer = ''
        self._md_in_code = False
        self._md_last_tag = None
        self._md_links = []
        self._md_copies = 0

    def apply_theme(self, theme_name=None):
        """刷新 markdown tag 颜色 (主题切换时调用)."""
        if theme_name is not None:
            self._theme = MD_COLORS.get(theme_name, self._theme)
        c = self._theme
        self.tag_configure('md_code', background=c.get('code_bg', ''),
                           foreground=c.get('code_fg', ''))
        self.tag_configure('md_code_block', background=c.get('code_bg', ''),
                           foreground=c.get('code_fg', ''),
                           lmargin1=12, lmargin2=12,
                           spacing1=6, spacing3=6)
        self.tag_configure('md_h1', foreground=c.get('h1', ''),
                           font=self._font_variant(2, 'bold'))
        self.tag_configure('md_h2', foreground=c.get('h2', ''),
                           font=self._font_variant(1, 'bold'))
        self.tag_configure('md_h3', foreground=c.get('h2', ''),
                           font=self._font_variant(0, 'bold'))
        self.tag_configure('md_bold', font=self._font_variant(0, 'bold'))
        self.tag_configure('md_italic', font=self._font_variant(0, 'italic'))
        self.tag_configure('md_strike', overstrike=1,
                           foreground=c.get('strike', ''))
        self.tag_configure('md_list', lmargin1=16, lmargin2=16)
        for lv in range(1, 4):   # 嵌套列表缩进级别
            self.tag_configure('md_list_%d' % lv,
                               lmargin1=16 + lv * 16,
                               lmargin2=16 + lv * 16)
        self.tag_configure('md_quote', lmargin1=10, lmargin2=10,
                           background=c.get('quote_bg', ''),
                           foreground=c.get('quote', ''))
        for lv in (2, 3):   # 多级引用逐级缩进
            self.tag_configure('md_quote_%d' % lv,
                               lmargin1=10 + (lv - 1) * 12,
                               lmargin2=10 + (lv - 1) * 12,
                               background=c.get('quote_bg', ''),
                               foreground=c.get('quote', ''))
        self.tag_configure('md_hr', foreground=c.get('hr', ''),
                           spacing1=6, spacing3=6)
        self.tag_configure('md_lang', foreground=c.get('quote', ''))
        # 表格: 正文色 (继承 Text fg) + 极浅背景 + 块间距 — 与代码块区分
        self.tag_configure('md_table', background=c.get('table_bg', ''),
                           spacing1=4, spacing3=4)
        for tag in self._md_links:
            self.tag_configure(tag, foreground=c.get('link', ''),
                               underline=1)

    # ---- 段级缓冲 ----

    def _render_buf(self, buf):
        self._md_in_code = self._render_segment(buf, self._md_last_tag)

    def _render_stable(self):
        """渲染缓冲中的稳定段 (空行分隔且不在代码块内), 末段保留."""
        while True:
            buf = self._md_buffer
            in_code = self._md_in_code
            pos = 0
            cut = -1
            for line in buf.splitlines(keepends=True):
                s = line.strip()
                if s.startswith('```'):
                    in_code = not in_code
                if not in_code and s == '':
                    cut = pos + len(line)
                    break
                pos += len(line)
            if cut == -1:
                return
            seg = buf[:cut]
            self._md_buffer = buf[cut:].lstrip('\n')
            self._with_editable(self._render_buf, seg)

    # ---- 块级渲染 ----

    def _render_segment(self, seg, base_tag):
        """渲染一段完整文本, 返回渲染后的代码块状态.

        段以空行结尾; 若代码块意外未闭合 (防御), 未闭合块体放回缓冲。
        """
        if not seg.endswith('\n'):
            seg += '\n'   # flush 渲染的缓冲可能无尾换行 — 补齐, 防止末行被 split[:-1] 切掉
        in_code = self._md_in_code
        block = []
        block_lang = ''    # 代码块语言标记 (```python)
        prev_list = None   # 上一行列表 tag (续行对齐用)
        lines = seg.split('\n')[:-1]   # 尾部空行不处理
        last_blank = True              # 段首视为已有分隔 (折叠连续空行)
        i = 0
        while i < len(lines):
            line = lines[i]
            s = line.strip()
            indent = len(line) - len(line.lstrip())
            if in_code:
                if s.startswith('```'):
                    self._insert_code_block(block, block_lang)
                    block = []
                    block_lang = ''
                    in_code = False
                else:
                    block.append(line)
                i += 1
                continue
            if s.startswith('```'):
                in_code = True
                block = []
                block_lang = s[3:].strip()
                i += 1
                continue
            if _TABLE_ROW.match(s) and not _TABLE_SEP.match(s):
                rows = []
                while i < len(lines):
                    ls = lines[i].strip()
                    if _TABLE_ROW.match(ls):
                        rows.append(ls)
                        i += 1
                    else:
                        break
                self._insert_table(rows)
                prev_list = None
                last_blank = False
                continue
            if _HR.match(s):
                self.insert(tk.END, '─' * self.HR_WIDTH + '\n', ('md_hr',))
                prev_list = None
                last_blank = False
                i += 1
                continue
            if s.startswith('#'):
                level = len(s) - len(s.lstrip('#'))
                tag = {'1': 'md_h1', '2': 'md_h2'}.get(str(level), 'md_h3')
                # 标题也走行内解析 — `# 使用 \`MarkdownText\`` 这类写法常见
                self._insert_inline(s.lstrip('#').strip() + '\n', (tag,))
                prev_list = None
                last_blank = False
                i += 1
                continue
            if s.startswith('>'):
                # 引用块: '│' 左边线 + 浅背景, 多级 > 逐级缩进
                level = min(3, len(s) - len(s.lstrip('>')))
                tag = 'md_quote' if level == 1 else 'md_quote_%d' % level
                self._insert_inline('│ ' + s.lstrip('>').strip() + '\n',
                                    (tag,))
                prev_list = None
                last_blank = False
                i += 1
                continue
            m_task = _TASK.match(s)
            if m_task:
                tag = self._list_tag(indent)
                box = '☑ ' if m_task.group(1).lower() == 'x' else '☐ '
                self._insert_inline(box + m_task.group(2) + '\n', (tag,))
                prev_list = tag
                last_blank = False
                i += 1
                continue
            m = _ORDERED.match(s)
            if m:
                tag = self._list_tag(indent)
                self._insert_inline(m.group(1) + m.group(2) + '\n', (tag,))
                prev_list = tag
                last_blank = False
                i += 1
                continue
            if s.startswith(('- ', '* ')):
                tag = self._list_tag(indent)
                self._insert_inline('• ' + s[2:] + '\n', (tag,))
                prev_list = tag
                last_blank = False
                i += 1
                continue
            if s == '':
                if not last_blank:
                    self.insert(tk.END, '\n')
                last_blank = True
                prev_list = None
                i += 1
                continue
            if indent >= 2 and prev_list:
                # 列表续行: 与所属列表项同级别缩进
                self._insert_inline(s + '\n', (prev_list,))
                last_blank = False
                i += 1
                continue
            self._insert_inline(line + '\n', base_tag)
            prev_list = None
            last_blank = False
            i += 1
        if in_code:
            # 防御: 段尾仍在代码块内 — 未闭合块体放回缓冲
            self._md_buffer = ('\n'.join(block) + '\n'
                               if block else '') + self._md_buffer
        return in_code

    # ---- 行内渲染 ----

    @staticmethod
    def _list_tag(indent):
        """列表缩进级别 → tag (嵌套列表逐级缩进)."""
        level = min(3, indent // 2)
        return 'md_list' if level == 0 else 'md_list_%d' % level

    def _insert_inline(self, line, base_tag):
        """行内样式切分渲染; base_tag 可为 str 或 tag 元组."""
        if isinstance(base_tag, tuple):
            tags = base_tag
        else:
            tags = (base_tag,) if base_tag else ()
        # 转义字符 \X → 私有区占位 (不参与样式正则, 插入时还原)
        line = _escape(line)
        pos = 0
        for m in _INLINE_RE.finditer(line):
            if m.start() > pos:
                self._ins(line[pos:m.start()], tags)
            if m.group(2):
                self._ins(m.group(2), tags + ('md_bold', 'md_italic'))
            elif m.group(4):
                self._ins(m.group(4), tags + ('md_bold',))
            elif m.group(6):
                self._ins(m.group(6), tags + ('md_bold',))
            elif m.group(8):
                self._ins(m.group(8), tags + ('md_italic',))
            elif m.group(10):
                self._ins(m.group(10), tags + ('md_code',))
            elif m.group(12):
                self._ins(m.group(12), tags + ('md_strike',))
            elif m.group(14):
                self._insert_link(m.group(14), m.group(15), tags)
            elif m.group(16):
                # 裸 URL 常尾随句读 (参见 https://x.com。) — 剥落后作为纯文本补回
                url = m.group(16)
                stripped = url.rstrip('.,;:!?)]}，。；：！？、')
                trailing = url[len(stripped):]
                self._insert_link(stripped, stripped, tags)
                if trailing:
                    self._ins(trailing, tags)
            pos = m.end()
        if pos < len(line):
            self._ins(line[pos:], tags)

    def _ins(self, text, tags):
        """插入并还原转义占位 (私有区字符 → 原字符)."""
        self.insert(tk.END, _unescape(text), tags)

    def _insert_link(self, text, url, tags):
        """链接: http/https 可点击 (tag_bind + webbrowser), 其余仅显示."""
        url = url.strip()
        if not url.startswith(('http://', 'https://')):
            self.insert(tk.END, text, tags)
            return
        n = len(self._md_links)
        tag = 'md_link_%d' % n
        self.tag_configure(tag, foreground=self._theme.get('link', ''),
                           underline=1)
        self.tag_bind(tag, '<Button-1>',
                      lambda _e, u=url: webbrowser.open(u))
        self.tag_bind(tag, '<Enter>',
                      lambda _e: self.config(cursor='hand2'))
        self.tag_bind(tag, '<Leave>',
                      lambda _e: self.config(cursor=''))
        self._md_links.append(tag)
        self.insert(tk.END, text, tags + (tag,))

    # ---- 表格 ----

    def _insert_table(self, rows):
        """表格: 首行表头 (若次行是分隔), 按显示宽度对齐文本输出.

        分隔行的冒号控制列对齐 (:--: 居中 / --: 右对齐 / 缺省左对齐)。
        """
        parsed = []
        header = False
        aligns = []
        for r in rows:
            if _TABLE_SEP.match(r):
                header = bool(parsed)   # 分隔行前的首行是表头
                # 冒号对齐标记: ':---' 左, '---:' 右, ':---:' 居中
                aligns = []
                for cell in r.strip().strip('|').split('|'):
                    c = cell.strip()
                    if c.startswith(':') and c.endswith(':'):
                        aligns.append('c')
                    elif c.endswith(':'):
                        aligns.append('r')
                    else:
                        aligns.append('l')
                continue
            cells = [c.strip() for c in r.strip().strip('|').split('|')]
            parsed.append(cells)
        if not parsed:
            return
        ncols = max(len(c) for c in parsed)
        parsed = [c + [''] * (ncols - len(c)) for c in parsed]
        aligns = (aligns + ['l'] * ncols)[:ncols]
        widths = [max(_disp_width(c[j]) for c in parsed)
                  for j in range(ncols)]
        head = parsed[0] if header else None
        body = parsed[1:] if header else parsed
        if head:
            self.insert(tk.END, _fmt_row(head, widths, aligns) + '\n',
                        ('md_table', 'md_bold'))
            self.insert(tk.END,
                        '|' + '|'.join('-' * (w + 2) for w in widths) + '|\n',
                        ('md_table',))
        for cells in body:
            self.insert(tk.END, _fmt_row(cells, widths, aligns) + '\n',
                        ('md_table',))

    # ---- 代码块 ----

    def _insert_code_block(self, block, lang=''):
        """代码块: 逐行 code_block tag + 尾随 '语言 [复制]' 文本标签
        (纯文本, 不用 window_create — 嵌入 window 会阻断文本拖选)."""
        if not block:
            return
        for line in block:
            self.insert(tk.END, line + '\n', ('md_code_block',))
        n = self._md_copies
        self._md_copies += 1
        tag = 'md_copy_%d' % n
        self.tag_configure(tag, foreground=self._theme.get('link', ''))
        self.tag_bind(tag, '<Button-1>',
                      lambda _e, b=list(block): self._copy_block(b))
        self.tag_bind(tag, '<Enter>',
                      lambda _e: self.config(cursor='hand2'))
        self.tag_bind(tag, '<Leave>',
                      lambda _e: self.config(cursor=''))
        # 块尾行: 语言标记 (如有, hint 色) + [复制] (link 色)
        if lang:
            self.insert(tk.END, lang + '  ', ('md_code_block', 'md_lang'))
        self.insert(tk.END, f"[{self._lang['copy']}]", ('md_code_block', tag))
        self.insert(tk.END, '\n\n')

    def _copy_block(self, block):
        text = '\n'.join(block)
        self.clipboard_clear()
        self.clipboard_append(text)

    # ---- 工具 ----

    def _with_editable(self, fn, *args):
        """渲染期间临时放开 DISABLED 状态 (insert 要求可编辑)."""
        state = self.cget('state')
        if state != tk.NORMAL:
            self.config(state=tk.NORMAL)
        try:
            fn(*args)
        finally:
            if state != tk.NORMAL:
                self.config(state=state)

    def _font_variant(self, dsize, *styles):
        """基于当前字体派生变体 (标题加粗/大字号, 斜体等)."""
        f = self.cget('font')
        if isinstance(f, tuple) and f:
            size = max(8, int(f[1]) + dsize)
            return (f[0], size) + tuple(styles)
        return ('TkFixedFont', 10 + dsize) + tuple(styles)

    def delete(self, *args):
        """清空时链接/复制标签一并失效 (tag 随文本删除)."""
        super().delete(*args)
        self._md_links = []
        self._md_copies = 0
