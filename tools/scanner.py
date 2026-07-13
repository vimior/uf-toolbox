# -*- coding: utf-8 -*-
"""Tool discovery — scans directories, reads config, returns menu entries."""
import json
import os
import shutil
import subprocess
import sys
from common.common import get_logger

logger = get_logger()

_running = {}  # name -> [Popen, ...]


def scan_tools(lang='en', menu=None, path=None):
    """Return {'tools': [...], 'groups': [...]}, optionally filtered by *menu* key."""
    all_tools = []
    all_groups = []
    dirs = _resolve_dirs(path)
    for tools_dir in dirs:
        if not os.path.isdir(tools_dir):
            continue
        cfg_path = None
        if sys.platform != 'win32':
            linux_cfg = os.path.join(tools_dir, 'tools_linux.json')
            if os.path.isfile(linux_cfg):
                cfg_path = linux_cfg
        if cfg_path is None:
            cfg_path = os.path.join(tools_dir, 'tools.json')
        if os.path.isfile(cfg_path):
            result = _from_config(tools_dir, cfg_path, lang)
        else:
            result = _from_scan(tools_dir)
        all_tools.extend(result.get('tools', []))
        all_groups.extend(result.get('groups', []))
    if menu:
        all_groups = [g for g in all_groups if g.get('menu', 'tools') == menu]
        all_tools = [t for t in all_tools if t.get('menu', 'tools') == menu]
    return {'tools': all_tools, 'groups': all_groups}


def launch(tool):
    """Spawn a tool process. *tool* is a dict from scan_tools()."""
    name = tool['name']
    if not tool.get('multiple', True) and name in _running:
        for p in _running[name]:
            if p.poll() is None:
                return p
    cmd = _build_cmd(tool)
    cwd = tool.get('cwd', '')
    env = tool.get('env')
    shell = tool.get('shell', True)
    flags = _creation_flags(tool)
    logger.info(f'[Tool] {name}  ->  {cmd}')
    if name not in _running:
        _running[name] = []
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, shell=shell,
        creationflags=flags)
    if tool.get('kill_on_exit', False):
        _running[name].append(proc)
    if tool.get('wait', False):
        proc.wait()
    return proc


def kill_all():
    """Terminate all tracked tool processes (with process tree)."""
    for name, procs in list(_running.items()):
        for proc in procs:
            try:
                if sys.platform == 'win32':
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                        capture_output=True)
                else:
                    proc.terminate()
            except Exception:
                pass
    _running.clear()


def _build_cmd(tool):
    exe_path = tool['_exe_path']
    args = tool.get('args', '')
    if tool.get('run_as_admin', False) and sys.platform == 'win32':
        return f'powershell -Command "Start-Process \'{exe_path}\' -Verb RunAs"'
    if tool.get('console', False) and sys.platform == 'win32':
        return f'start "" "{exe_path}" {args}'.strip()
    if args:
        return f'"{exe_path}" {args}'
    return exe_path


def _creation_flags(tool):
    if sys.platform != 'win32':
        return 0
    if tool.get('console', False):
        return 0
    return subprocess.CREATE_NO_WINDOW


def _resolve_dirs(path=None):
    if getattr(sys, 'frozen', False):
        dirs = [os.path.join(sys._MEIPASS, 'tools')]
        base = os.path.dirname(sys.executable)
        tool_path = os.path.join(base, 'tools')
        if os.path.isdir(tool_path) and tool_path not in dirs:
            dirs.append(tool_path)
        if path and path != 'tools':
            tool_path = os.path.join(base, path)
            if os.path.isdir(tool_path) and tool_path not in dirs:
                dirs.append(tool_path)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs = [
            os.path.join(base, 'tools'),
            os.path.join(base, 'dist', 'tools'),
        ]
        if path and path != 'tools':
            dirs.append(os.path.join(base, 'dist', path))
    return dirs


def _resolve_name(entry, lang):
    """Pick the right display name based on language."""
    name = entry.get('name', '')
    if lang.startswith('zh') and entry.get('name_zh'):
        return entry['name_zh']
    if lang == 'en' and entry.get('name_en'):
        return entry['name_en']
    return name


def _parse_tool(tools_dir, entry, lang):
    """Parse a single tool entry into the internal dict."""
    name = _resolve_name(entry, lang)
    exe = entry.get('path', '')
    if not name or not exe:
        return None
    exe_path = os.path.join(tools_dir, exe)
    if not os.path.isfile(exe_path):
        resolved = shutil.which(exe)
        if resolved:
            exe_path = resolved
    return {
        'name': name,
        '_exe_path': exe_path,
        'args': entry.get('args', ''),
        'cwd': entry.get('cwd', '') or tools_dir,
        'shell': entry.get('shell', True),
        'env': entry.get('env'),
        'console': entry.get('console', False),
        'run_as_admin': entry.get('run_as_admin', False),
        'wait': entry.get('wait', False),
        'multiple': entry.get('multiple', True),
        'kill_on_exit': entry.get('kill_on_exit', False),
        'menu': entry.get('menu', 'tools'),
    }


def _from_config(tools_dir, cfg_path, lang):
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception:
        return {'tools': [], 'groups': []}
    entries = [_parse_tool(tools_dir, e, lang)
               for e in cfg.get('tools', []) if _parse_tool(tools_dir, e, lang)]
    groups = _parse_groups(tools_dir, cfg.get('groups', []), lang)
    return {'tools': entries, 'groups': groups}


def _parse_groups(tools_dir, raw_groups, lang):
    """Recursively parse nested groups."""
    result = []
    for g in raw_groups:
        grp = {'name': _resolve_name(g, lang), 'tools': [], 'groups': [],
               'menu': g.get('menu', 'tools')}
        for entry in g.get('tools', []):
            t = _parse_tool(tools_dir, entry, lang)
            if t:
                grp['tools'].append(t)
        if g.get('groups'):
            grp['groups'] = _parse_groups(tools_dir, g['groups'], lang)
        if grp['tools'] or grp['groups']:
            result.append(grp)
    return result


def _from_scan(tools_dir):
    entries = []
    exts = ('.exe', '.bat', '.cmd') if sys.platform == 'win32' \
        else ('', '.sh', '.py')
    for fn in sorted(os.listdir(tools_dir)):
        if fn == 'tools.json':
            continue
        path_ = os.path.join(tools_dir, fn)
        if os.path.isfile(path_) and fn.endswith(exts):
            entries.append({
                'name': fn,
                '_exe_path': path_,
                'args': '',
                'cwd': tools_dir,
                'shell': True,
                'env': None,
                'console': False,
                'run_as_admin': False,
                'wait': False,
                'multiple': True,
                'kill_on_exit': False,
                'menu': 'tools',
            })
    return {'tools': entries, 'groups': []}
