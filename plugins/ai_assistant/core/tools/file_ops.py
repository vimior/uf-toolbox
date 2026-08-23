# -*- coding: utf-8 -*-
"""文件工具组 — read_file / write_file / list_dir.

FileTools 统一承载文件操作: 共享路径展开与大小格式化; 方法经
@tool_spec 标记, 实例化时扫描注册 (绑定方法, 签名即 schema)。
"""
import os

from ..registry import register_tools_from, tool_spec

_MAX_BODY = 64 * 1024   # 工具返回体截断上限 (同 http tab)


def _expand_path(path):
    return os.path.abspath(os.path.expanduser(str(path or '').strip()))


def _human_size(n):
    if n >= 1024 * 1024:
        return '%.1f MB' % (n / 1024 / 1024)
    if n >= 1024:
        return '%.1f KB' % (n / 1024)
    return '%d B' % n


# ---------------------------------------------------------------------------
# 面板摘要 (summary) — 一行展示用, 解析失败返回 None 由面板回退截取
# ---------------------------------------------------------------------------


def _write_summary(result, args=None):
    path = _expand_path((args or {}).get('path') or '')
    content = (args or {}).get('content') or ''
    return '%s (%d 字符)' % (path, len(str(content)))


def _read_summary(result, args=None):
    path = _expand_path((args or {}).get('path') or '')
    size = len(str(result or ''))
    return '%s (%d 字符)' % (path, size)


def _list_summary(result, args=None):
    path = _expand_path((args or {}).get('path') or '.')
    n = len(str(result or '').splitlines()) if result else 0
    return '%s: %d 项' % (path, n)


class FileTools:
    """内置文件操作工具 — @tool_spec 标记的方法在实例化时注册."""

    def __init__(self, registry):
        register_tools_from(registry, self)

    @tool_spec(dangerous=True, summary=_write_summary)
    def write_file(self, path: str, content: str) -> str:
        """用户要求生成或写入文件内容时使用 (覆盖写, 自动创建父目录; 执行前需用户确认)。
        path: 文件路径, 支持 ~ 展开
        content: 文件内容"""
        path = str(path or '').strip()
        if not path:
            return 'empty path'
        path = _expand_path(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # newline='' — 忠实写入模型内容 (禁止 Windows 换行转换, 保持 LF)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        size = len(content.encode('utf-8', errors='replace'))
        return '已写入 %d 字节 → %s' % (size, path)

    @tool_spec(summary=_read_summary)
    def read_file(self, path: str) -> str:
        """用户要求读取或查看文件内容时使用 (64KB 截断)。
        path: 文件路径, 支持 ~ 展开"""
        path = _expand_path(path)
        if not path or not os.path.isfile(path):
            return 'file not found: %s' % (path or '(empty)')
        with open(path, 'rb') as f:
            data = f.read(_MAX_BODY + 1)
        truncated = len(data) > _MAX_BODY
        data = data[:_MAX_BODY]
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            text = data.decode('gbk', errors='replace')
        if truncated:
            text += '\n(truncated)'
        return text

    @tool_spec(summary=_list_summary)
    def list_dir(self, path: str = '.') -> str:
        """用户要求查看目录内容时使用 (名称/类型/大小)。
        path: 目录路径, 默认当前目录"""
        path = _expand_path(path)
        try:
            names = sorted(os.listdir(path))
        except OSError as e:
            return 'list error: %s' % e
        lines = []
        for name in names:
            full = os.path.join(path, name)
            if os.path.isdir(full):
                lines.append('%s/' % name)
            else:
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                lines.append('%s (%s)' % (name, _human_size(size)))
        return '\n'.join(lines) or '(empty)'
