# -*- coding: utf-8 -*-
"""Tool discovery and lifecycle management — standalone, no external dependencies."""
import json
import os
import shutil
import subprocess
import sys
from typing import Literal


class ToolManager:
    """Manages tool discovery, launch, and lifecycle.

    Usage::

        from common.common import logger
        tm = ToolManager(logger)
        result = tm.scan(lang, tab='tools')
        tm.launch(tool_dict)
        tm.kill_all()

    *app* 可选 — 传入后自动注册 agent 工具 ``tools_operation``
    (需要 app 提供 tool_path / current_lang_name); standalone
    使用时不传, 无任何项目依赖。
    """

    def __init__(self, logger, app=None):
        self.logger = logger
        self.app = app
        self._running = {}  # name -> [Popen, ...]
        self.register_agent_tools()

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

    def launch(self, tool, run_as_admin=False):
        """Spawn a tool process. *tool* is a dict from scan()."""
        name = tool['name']
        if not tool.get('multiple', True) and name in self._running:
            for p in self._running[name]:
                if p.poll() is None:
                    return p
        cmd = self._build_cmd(tool, run_as_admin=run_as_admin)
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
            'privilege_level': entry.get('privilege_level', 'user'),
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
                    'privilege_level': 'user',
                    'wait': False,
                    'multiple': True,
                    'kill_on_exit': False,
                    'tab': 'tools',
                })
        return {'tools': entries, 'groups': []}

    @staticmethod
    def _build_cmd(tool, run_as_admin=False):
        exe_path = tool['_exe_path']
        args = tool.get('args', '')
        if run_as_admin and sys.platform == 'win32':
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

    # -- Agent ---------------------------------------------------------

    def register_agent_tools(self):
        if self.app is not None:
            # 注册 agent 工具
            # 惰性 import — 保持模块 standalone (无 app 时不引入项目依赖)。
            from plugins.ai_assistant.core.registry import registry as agent_registry
            agent_registry.register('tools_operation', fn=self.agent_tools)

    def agent_tools(self,
        action: Literal['list', 'launch'],
        target: str = '',
        run_as_admin: bool = False,
        tab: str = ''):
        """
        启动外部程序: launch必须传target

        action: launch=启动指定工具(首选:直接传名称即可,支持模糊匹配,未命中自动返回可用清单);list=列出全部工具(仅需要浏览有哪些工具时用)
        target: 仅launch: 外部程序的id/显示名/exe文件名(支持模糊,唯一匹配即可)
        run_as_admin: 仅launch: 是否以管理员方式打开
        tab: 分组标签过滤(如tools/system),省略=全部
        """
        lang = getattr(self.app, 'current_lang_name', 'en')
        path = getattr(self.app, 'tool_path', None)
        tab = tab.strip() or None
        if action == 'list':
            tools = self.flatten(self.scan(lang, tab=tab, path=path))
            # 太长会被结果截断, 导致模型漏看尾部条目
            # 紧凑格式: name1(id1)|name2(id2)|...
            return '|'.join(
                '%s(%s)' % (t['name'], t['id']) if t.get('id')
                else t['name'] for t in tools) or '(无可用工具)'
        if action != 'launch':
            return 'error: unknown action %r' % action
        if not target.strip():
            return 'error: target is required'
        tool, cands, all_tools = self.resolve(target, lang, tab=tab,
                                              path=path)
        if tool is None:
            # 错误尾部互相指引 — 模型首次选错工具时第二轮必中
            # hint = ' 如果你要打开的是 UF Toolbox 插件, 请改用 plugins_operation'
            hint = ''
            avail = '; '.join('%s(%s)' % (t.get('name'), t.get('id'))
                              for t in all_tools) or '(无)'
            if cands:
                opts = '; '.join('%s(%s)' % (t.get('name'), t.get('id'))
                                 for t in cands)
                return ('error: %r 匹配到多个工具: %s. 可用工具: %s.%s'
                        % (target, opts, avail, hint))
            return ('error: %r 未匹配到工具. 可用工具: %s.%s'
                    % (target, avail, hint))
        try:
            self.launch(tool, run_as_admin=run_as_admin)
        except Exception as e:
            return 'error: 启动失败: %s' % e
        return 'ok: 已启动 %s' % tool.get('name')

    # -- agent 支持: 扁平化 + 名称解析 ----------------------------------------
        
    @staticmethod
    def flatten(scan_result):
        """scan() 结果 → 扁平工具列表 (groups 递归展开, 顶层在后)."""
        flat = []

        def _walk(groups):
            for g in groups:
                flat.extend(g.get('tools', []))
                _walk(g.get('groups', []))

        _walk(scan_result.get('groups', []))
        flat.extend(scan_result.get('tools', []))
        return flat

    _STRIP_EXTS = ('.exe', '.bat', '.cmd', '.sh', '.py')

    @staticmethod
    def _norm(s):
        """归一化匹配串: 小写 + 去 -_ 和空格 (uf-teleop ≡ UFTeleop)."""
        return s.lower().replace('-', '').replace('_', '').replace(' ', '')

    @classmethod
    def _match_map(cls, tool):
        """工具的分层匹配键 (归一化): id 全串 / id 末段 / 显示名 / exe basename.

        分层原因: 同一 exe 可能被多个工具引用 (cmd.exe → 运行/管理员运行/
        安全中心), basename 同级比较必然歧义; id 末段先比可唯一命中。
        """
        m = {}
        tid = tool.get('id')
        if tid:
            m['id'] = cls._norm(tid)
            m['id_tail'] = cls._norm(tid.split('/')[-1])
        if tool.get('name'):
            m['name'] = cls._norm(tool['name'])
        base = os.path.basename(tool.get('_exe_path', ''))
        for ext in cls._STRIP_EXTS:
            if base.lower().endswith(ext):
                base = base[:-len(ext)]
                break
        if base:
            m['base'] = cls._norm(base)
        return m

    _TIERS = ('id', 'id_tail', 'name', 'base')

    def resolve(self, query, lang='en', tab=None, path=None):
        """按名称解析工具: id → id末段 → 显示名 → exe名 分层精确 → 唯一模糊.

        返回 (tool | None, candidates, all_tools) — candidates 仅在
        歧义/多候选时非空, 供错误提示; query 未匹配任何工具时为空。
        匹配归一化 (小写, 去 -_ 空格); query 带扩展名会被剥掉。
        """
        q = query.strip()
        for ext in self._STRIP_EXTS:
            if q.lower().endswith(ext):
                q = q[:-len(ext)]
                break
        nq = self._norm(q)
        tools = self.flatten(self.scan(lang, tab=tab, path=path))
        if not nq:
            return None, [], tools
        maps = [(t, self._match_map(t)) for t in tools]
        for tier in self._TIERS:
            hits = [t for t, m in maps if m.get(tier) == nq]
            if len(hits) == 1:
                return hits[0], [], tools
            if hits:
                return None, hits, tools
        fuzzy = [t for t, m in maps
                    if any(nq in k or k in nq for k in m.values())]
        if len(fuzzy) == 1:
            return fuzzy[0], [], tools
        return None, fuzzy, tools
