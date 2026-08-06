# -*- coding: utf-8 -*-
"""Plugin development guide — loads and renders docs/plugin-guide.md."""
import os
import re
import tkinter as tk
from plugins.plugin import GuiPlugin

STYLE = {
    'dark': {
        'bg': '#1e1e1e',       'frame': '#252525',
        'fg': '#cccccc',       'h1': '#ffffff',
        'h2': '#e0e0e0',       'code_bg': '#1a1a1a',
        'code_fg': '#ce9178',  'link': '#569cd6',
        'th': '#9cdcfe',       'bar': '#333333',
        'bar_fg': '#ffffff',   'hr': '#444444',
        'scroll_frame': '#252525', 'scroll_bar': '#333333',
    },
    'light': {
        'bg': '#ffffff',       'frame': '#f5f5f5',
        'fg': '#333333',       'h1': '#222222',
        'h2': '#444444',       'code_bg': '#f0f0f0',
        'code_fg': '#a31515',  'link': '#0066cc',
        'th': '#0066cc',       'bar': '#e0e0e0',
        'bar_fg': '#333333',   'hr': '#cccccc',
        'scroll_frame': '#f5f5f5', 'scroll_bar': '#e0e0e0',
    },
}


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
        theme_name = self.app.current_theme_name
        s = STYLE.get(theme_name, STYLE['dark'])

        self.title(self.name_zh if lang_name == 'zh' else self.name_en)
        self.geometry("820x600")
        self.resizable(True, True)
        self.configure(bg=s['bg'])

        # ---- header ----
        hdr = tk.Frame(self, bg=s['bar'], height=28)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        title = f"  {self.name_en if lang_name == 'en' else self.name_zh}"
        tk.Label(hdr, text=title, bg=s['bar'], fg=s['bar_fg'],
                 font=("Microsoft YaHei", 9, "bold")).pack(
            side=tk.LEFT, padx=14, pady=4)

        # ---- body ----
        outer = tk.Frame(self, bg=s['bg'])
        outer.pack(fill=tk.BOTH, expand=True, padx=(16, 4), pady=(12, 8))

        scrollbar = tk.Scrollbar(outer, orient=tk.VERTICAL,
                                 width=12, relief=tk.FLAT, borderwidth=0,
                                 bg=s['scroll_bar'], troughcolor=s['scroll_frame'])
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._txt = tk.Text(outer, wrap=tk.WORD, font=("Consolas", 10),
                            bg=s['frame'], fg=s['fg'], relief=tk.FLAT,
                            padx=18, pady=14, borderwidth=0,
                            highlightthickness=0, insertbackground=s['fg'],
                            tabs=("1.5c",),
                            yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._txt.yview)
        self._txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ---- tags ----
        self._txt.tag_configure("h1", font=("Consolas", 16, "bold"),
                                foreground=s['h1'], spacing3=4)
        self._txt.tag_configure("h2", font=("Consolas", 13, "bold"),
                                foreground=s['h2'], spacing3=3)
        self._txt.tag_configure("h3", font=("Consolas", 11, "bold"),
                                foreground=s['h2'], spacing3=2)
        self._txt.tag_configure("b", font=("Consolas", 10, "bold"))
        self._txt.tag_configure("i", font=("Consolas", 10, "italic"))
        self._txt.tag_configure("code", font=("Consolas", 10),
                                background=s['code_bg'], foreground=s['code_fg'])
        self._txt.tag_configure("code_block", font=("Consolas", 9),
                                background=s['code_bg'], lmargin1=12,
                                lmargin2=12, rmargin=12, spacing1=3, spacing3=3)
        self._txt.tag_configure("hr", foreground=s['hr'],
                                font=("Consolas", 1), spacing1=8, spacing3=8)
        self._txt.tag_configure("list", lmargin1=24, lmargin2=32)
        self._txt.tag_configure("th", font=("Consolas", 10, "bold"),
                                foreground=s['th'])
        self._txt.tag_configure("link", foreground=s['link'], underline=True)

        # ---- load & render ----
        self._render_markdown(self._load_doc(lang_name))
        self._txt.configure(state=tk.DISABLED)

        # ---- mousewheel ----
        def _scroll(event):
            self._txt.yview_scroll(int(-1 * (event.delta / 120)), "units")
        _bound = [False]

        def _enter(e):
            if not _bound[0]:
                self._txt.bind_all("<MouseWheel>", _scroll)
                _bound[0] = True

        def _leave(e):
            if _bound[0]:
                self._txt.unbind_all("<MouseWheel>")
                _bound[0] = False

        self._txt.bind("<Enter>", _enter, add="+")
        self._txt.bind("<Leave>", _leave, add="+")

    # ---- renderer ----

    def _render_markdown(self, text):
        lines = text.split('\n')
        i = 0
        in_code = False
        last_blank = False
        table_buf = []     # [(cells, is_header)]
        table_cols = 0

        def _tsep(s):
            return bool(re.match(r'^\|(\s*[\-:]+\s*\|)+$', s.strip()))

        def _trow(s):
            s = s.strip()
            return s.startswith('|') and s.endswith('|') and not _tsep(s)

        def _is_hd(s):
            return bool(re.match(r'^#{1,3}\s+', s))

        def _has_content(s):
            return s.strip() != '' and not s.startswith('```')

        def _clean_cell(s):
            """Strip backticks and markdown formatting from a table cell."""
            s = s.strip()
            s = re.sub(r'^`(.+)`$', r'\1', s)   # `code`
            s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
            s = re.sub(r'\*(.+?)\*', r'\1', s)
            return s

        def _flush_table():
            nonlocal table_buf, table_cols
            if not table_buf:
                return
            # Skip header row + separator (first entry if marked as header)
            rows = [(cells, h) for cells, h in table_buf if not h]
            if not rows:
                table_buf = []
                table_cols = 0
                return
            lines = [_format_table_row(cells, table_cols)
                     for cells, _ in rows]
            self._txt.insert(tk.END, '\n'.join(lines) + '\n', "code_block")
            table_buf = []
            table_cols = 0

        def _format_table_row(cells, ncols):
            c = [_clean_cell(x) for x in cells]
            if ncols == 4:
                return f"{c[0]}: [{c[1]}]({c[2]}), {c[3]}"
            if ncols == 2:
                return f"{c[0]} — {c[1]}"
            return ' | '.join(c)

        while i < len(lines):
            line = lines[i]
            nxt = lines[i + 1] if i + 1 < len(lines) else ""

            if line.startswith('```'):
                _flush_table()
                in_code = not in_code
                last_blank = False
                i += 1
                continue
            if in_code:
                self._txt.insert(tk.END, line + '\n', "code_block")
                i += 1
                continue

            m = re.match(r'^(#{1,3})\s+(.+)', line)
            if m:
                _flush_table()
                n = len(m.group(1))
                tag = {1: "h1", 2: "h2"}.get(n, "h3")
                self._insert_inline(m.group(2) + '\n', tag)
                last_blank = False
                i += 1
                continue

            if line.strip() == '---' and not _tsep(line):
                _flush_table()
                self._txt.insert(tk.END, '─' * 60 + '\n', "hr")
                last_blank = False
                i += 1
                continue

            if _tsep(line):
                # Previous row was the header — mark it
                if table_buf:
                    pcells, _ = table_buf[-1]
                    table_buf[-1] = (pcells, True)
                i += 1
                continue

            if _trow(line):
                cells = [c.strip() for c in line.strip().split('|')[1:-1]]
                if not table_buf:
                    table_cols = len(cells)
                table_buf.append((cells, False))
                last_blank = False
                i += 1
                continue

            # Non-table line — flush buffered table first
            _flush_table()

            m = re.match(r'^(\s*)([-*]|\d+\.)\s+(.+)', line)
            if m:
                indent = len(m.group(1))
                prefix = ' ' * indent + '• '
                self._insert_inline(prefix + m.group(3) + '\n', "list")
                last_blank = False
                i += 1
                continue

            if line.strip() == '':
                if not last_blank and (_is_hd(nxt) or _has_content(nxt)):
                    self._txt.insert(tk.END, '\n')
                    last_blank = True
                i += 1
                continue

            self._insert_inline(line + '\n')
            last_blank = False
            i += 1

        _flush_table()

    def _insert_inline(self, text, base_tag=None):
        tags = (base_tag,) if base_tag else ()
        pat = re.compile(
            r'(\*\*(.+?)\*\*)|'
            r'(\*(.+?)\*)|'
            r'(`(.+?)`)|'
            r'(\[(.+?)\]\((.+?)\))'
        )
        pos = 0
        for m in pat.finditer(text):
            if m.start() > pos:
                self._txt.insert(tk.END, text[pos:m.start()], tags)
            if m.group(2):
                self._txt.insert(tk.END, m.group(2), tags + ("b",))
            elif m.group(4):
                self._txt.insert(tk.END, m.group(4), tags + ("i",))
            elif m.group(6):
                self._txt.insert(tk.END, m.group(6), tags + ("code",))
            elif m.group(8):
                self._txt.insert(tk.END, m.group(8), tags + ("link",))
            pos = m.end()
        if pos < len(text):
            self._txt.insert(tk.END, text[pos:], tags)

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
