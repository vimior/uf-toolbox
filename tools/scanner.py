# -*- coding: utf-8 -*-
"""Tool discovery — scans directories, reads config, returns menu entries."""
import json
import os
import shutil
import subprocess
import sys
from common.common import logger

_running = {}  # name -> [Popen, ...]


def scan_tools(lang='en', tab=None, path=None):
    """Return {'tools': [...], 'groups': [...]}, optionally filtered by *tab*.

    Multiple directories are scanned in order; tools with duplicate IDs from
    later directories override earlier ones. Tools without IDs are appended."""
    tools_by_id = {}  # id -> tool (for dedup)
    all_tools_no_id = []
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
        for t in result.get('tools', []):
            tid = t.get('id')
            if tid:
                tools_by_id[tid] = t  # later overrides earlier
            else:
                all_tools_no_id.append(t)
        for g in result.get('groups', []):
            _merge_group(g, all_groups)
    # Cross-merge: top-level ID'd tools override matching tools inside groups
    _consumed_ids = set()
    if tools_by_id:
        for g in all_groups:
            _override_group_tools(g, tools_by_id, _consumed_ids)
    # Build final tools list: only un-consumed ID'd tools + un-identified
    all_tools = [t for tid, t in tools_by_id.items() if tid not in _consumed_ids]
    all_tools += all_tools_no_id
    if tab:
        all_groups = [g for g in all_groups if g.get('tab', 'tools') == tab]
        all_tools = [t for t in all_tools if t.get('tab', 'tools') == tab]
    return {'tools': all_tools, 'groups': all_groups}


def _override_group_tools(group, tools_by_id, consumed=None):
    """Replace tools in *group* (and sub-groups) with matching entries from *tools_by_id*.
    *consumed* tracks IDs that were used for override — those should not appear as top-level."""
    if consumed is None:
        consumed = set()
    for i, t in enumerate(group.get('tools', [])):
        tid = t.get('id')
        if tid and tid in tools_by_id:
            group['tools'][i] = tools_by_id[tid]
            consumed.add(tid)
    for sg in group.get('groups', []):
        _override_group_tools(sg, tools_by_id, consumed)


def _merge_group(src, dst_list):
    """Merge *src* group into *dst_list* by ID; if ID matches, merge tools recursively."""
    gid = src.get('id')
    if gid:
        for d in dst_list:
            if d.get('id') == gid:
                d['tools'].extend(src.get('tools', []))
                for sg in src.get('groups', []):
                    _merge_group(sg, d.setdefault('groups', []))
                return
    dst_list.append(src)


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
    tool_id = tool.get('id', '')
    flags = _creation_flags(tool)
    if tool_id:
        logger.info(f'[Tool:{tool_id}] {name}  ->  {cmd}')
    else:
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
    if lang.startswith('zh') and entry.get('name_cn'):
        return entry['name_cn']
    if lang == 'en' and entry.get('name_en'):
        return entry['name_en']
    return name


def _parse_tool(tools_dir, entry, lang, prefix=''):
    """Parse a single tool entry into the internal dict.

    *prefix* is the ID path from parent groups (e.g. 'system/common').
    The tool's full ID becomes 'prefix/tool_id'."""
    name = _resolve_name(entry, lang)
    exe = entry.get('path', '')
    if not name or not exe:
        return None
    exe_path = os.path.join(tools_dir, exe)
    if not os.path.isfile(exe_path):
        resolved = shutil.which(exe)
        if resolved:
            exe_path = resolved
    tool_id = entry.get('id', '')
    full_id = f'{prefix}/{tool_id}' if (prefix and tool_id) else (tool_id or None)
    # Derive tab from ID first segment, default 'tools'
    tab = full_id.split('/')[0] if full_id else 'tools'
    return {
        'id': full_id,
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
        'tab': tab,
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


def _parse_groups(tools_dir, raw_groups, lang, prefix=''):
    """Recursively parse nested groups. *prefix* is the ID path from ancestors."""
    result = []
    for g in raw_groups:
        gid = g.get('id', '')
        full_prefix = f'{prefix}/{gid}' if (prefix and gid) else (gid or prefix)
        # Derive tab from ID first segment, default 'tools'
        tab = full_prefix.split('/')[0] if full_prefix else 'tools'
        grp = {'id': full_prefix or None,
               'name': _resolve_name(g, lang), 'tools': [], 'groups': [],
               'tab': tab}
        for entry in g.get('tools', []):
            t = _parse_tool(tools_dir, entry, lang, prefix=full_prefix)
            if t:
                grp['tools'].append(t)
        if g.get('groups'):
            grp['groups'] = _parse_groups(tools_dir, g['groups'], lang, prefix=full_prefix)
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
                'tab': 'tools',
            })
    return {'tools': entries, 'groups': []}
