# -*- coding: utf-8 -*-
"""Tool discovery and lifecycle management — standalone, no external dependencies."""
import json
import os
import shutil
import subprocess
import sys


class ToolManager:
    """Manages tool discovery, launch, and lifecycle.

    Usage::

        from common.common import logger
        tm = ToolManager(logger)
        result = tm.scan(lang, tab='tools')
        tm.launch(tool_dict)
        tm.kill_all()
    """

    def __init__(self, logger):
        self.logger = logger
        self._running = {}  # name -> [Popen, ...]

    # -- public API -----------------------------------------------------------

    def scan(self, lang='en', tab=None, path=None):
        """Return {'tools': [...], 'groups': [...]}, optionally filtered by *tab*.

        Multiple directories are scanned in order; tools with duplicate IDs from
        later directories override earlier ones. Tools without IDs are appended."""
        tools_by_id = {}
        all_tools_no_id = []
        all_groups = []
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs = [os.path.join(base, 'tools')]    # built-in (always exists)
        if path:
            dirs.append(path)                   # external (absolute)
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
                result = self._from_config(tools_dir, cfg_path, lang)
            else:
                result = self._from_scan(tools_dir)
            for t in result.get('tools', []):
                tid = t.get('id')
                if tid:
                    tools_by_id[tid] = t
                else:
                    all_tools_no_id.append(t)
            for g in result.get('groups', []):
                self._merge_group(g, all_groups)
        # Cross-merge: top-level ID'd tools override matching tools inside groups
        consumed_ids = set()
        if tools_by_id:
            for g in all_groups:
                self._override_group_tools(g, tools_by_id, consumed_ids)
        # Build final tools list: only un-consumed ID'd tools + un-identified
        all_tools = [t for tid, t in tools_by_id.items() if tid not in consumed_ids]
        all_tools += all_tools_no_id
        if tab:
            all_groups = [g for g in all_groups if g.get('tab', 'tools') == tab]
            all_tools = [t for t in all_tools if t.get('tab', 'tools') == tab]
        return {'tools': all_tools, 'groups': all_groups}

    def launch(self, tool):
        """Spawn a tool process. *tool* is a dict from scan()."""
        name = tool['name']
        if not tool.get('multiple', True) and name in self._running:
            for p in self._running[name]:
                if p.poll() is None:
                    return p
        cmd = self._build_cmd(tool)
        cwd = tool.get('cwd', '')
        env = tool.get('env')
        shell = tool.get('shell', True)
        tool_id = tool.get('id', '')
        flags = self._creation_flags(tool)
        if tool_id:
            self.logger.info(f'[Tool:{tool_id}] {name}  ->  {cmd}')
        else:
            self.logger.info(f'[Tool] {name}  ->  {cmd}')
        if name not in self._running:
            self._running[name] = []
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env, shell=shell,
            creationflags=flags)
        if tool.get('kill_on_exit', False):
            self._running[name].append(proc)
        if tool.get('wait', False):
            proc.wait()
        return proc

    def kill_all(self):
        """Terminate all tracked tool processes (with process tree)."""
        for name, procs in list(self._running.items()):
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
        self._running.clear()

    # -- internal helpers -----------------------------------------------------

    @staticmethod
    def _override_group_tools(group, tools_by_id, consumed=None):
        """Replace tools in *group* (and sub-groups) with matching entries
        from *tools_by_id*. *consumed* tracks IDs that were used for override —
        those should not appear as top-level."""
        if consumed is None:
            consumed = set()
        for i, t in enumerate(group.get('tools', [])):
            tid = t.get('id')
            if tid and tid in tools_by_id:
                group['tools'][i] = tools_by_id[tid]
                consumed.add(tid)
        for sg in group.get('groups', []):
            ToolManager._override_group_tools(sg, tools_by_id, consumed)

    @staticmethod
    def _merge_group(src, dst_list):
        """Merge *src* group into *dst_list* by ID; if ID matches,
        merge tools recursively."""
        gid = src.get('id')
        if gid:
            for d in dst_list:
                if d.get('id') == gid:
                    d['tools'].extend(src.get('tools', []))
                    for sg in src.get('groups', []):
                        ToolManager._merge_group(
                            sg, d.setdefault('groups', []))
                    return
        dst_list.append(src)

    @staticmethod
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

    @staticmethod
    def _parse_entry(tools_dir, entry, lang, prefix=''):
        """Parse an entry — returns a group dict (has 'tools'), a tool dict (has
        '_exe_path'), or None (ignored / invalid).

        *prefix* is the ID path from parents (e.g. 'system/common')."""
        if entry.get('ignore', False):
            return None

        sub_tools = entry.get('tools')
        if sub_tools is not None:
            # Nested tools → this entry is a group
            gid = entry.get('id', '')
            full_prefix = f'{prefix}/{gid}' if (prefix and gid) else (gid or prefix)
            tab = full_prefix.split('/')[0] if full_prefix and '/' in full_prefix else 'tools'
            flat = []
            nested = []
            for e in sub_tools:
                p = ToolManager._parse_entry(
                    tools_dir, e, lang, prefix=full_prefix)
                if p is None:
                    continue
                if '_exe_path' in p:
                    flat.append(p)
                else:
                    nested.append(p)
            return {
                'id': full_prefix or None,
                'name': ToolManager._resolve_name(entry, lang),
                'tools': flat,
                'groups': nested,
                'tab': tab,
            }

        # Leaf: flat tool
        name = ToolManager._resolve_name(entry, lang)
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
        tab = full_id.split('/')[0] if full_id and '/' in full_id else 'tools'
        return {
            'id': full_id,
            'name': name,
            '_exe_path': exe_path,
            'args': entry.get('args', ''),
            'cwd': os.path.join(tools_dir, entry.get('cwd', '')) or tools_dir,
            'shell': entry.get('shell', True),
            'env': entry.get('env'),
            'console': entry.get('console', False),
            'run_as_admin': entry.get('run_as_admin', False),
            'wait': entry.get('wait', False),
            'multiple': entry.get('multiple', True),
            'kill_on_exit': entry.get('kill_on_exit', False),
            'tab': tab,
        }

    @staticmethod
    def _from_config(tools_dir, cfg_path, lang):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            return {'tools': [], 'groups': []}
        parsed_tools = []
        parsed_groups = []
        for e in cfg.get('tools', []):
            parsed = ToolManager._parse_entry(tools_dir, e, lang)
            if parsed is None:
                continue
            if 'tools' in parsed and '_exe_path' not in parsed:
                parsed_groups.append(parsed)
            else:
                parsed_tools.append(parsed)
        return {'tools': parsed_tools, 'groups': parsed_groups}

    @staticmethod
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

    @staticmethod
    def _build_cmd(tool):
        exe_path = tool['_exe_path']
        args = tool.get('args', '')
        if tool.get('run_as_admin', False) and sys.platform == 'win32':
            return (f'powershell -Command '
                    f'"Start-Process \'{exe_path}\' -Verb RunAs"')
        if tool.get('console', False) and sys.platform == 'win32':
            return f'start "" "{exe_path}" {args}'.strip()
        if args:
            return f'"{exe_path}" {args}'
        return exe_path

    @staticmethod
    def _creation_flags(tool):
        if sys.platform != 'win32':
            return 0
        if tool.get('console', False):
            return 0
        return subprocess.CREATE_NO_WINDOW
