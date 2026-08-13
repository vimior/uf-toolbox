# -*- coding: utf-8 -*-
"""Plugin repository client — fetch index, scan local, download & install."""
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

# ---- constants ----

REPO_INDEX_URL_DEFAULT = "http://192.168.1.19/releases/uf-toolbox/plugins.json"
TIMEOUT = 10
STORE_INFO_FILE = ".store_info.json"

# 禁用系统代理检测 (避免 Windows WPAD 造成 10+ 秒延迟)
_no_proxy_handler = urllib.request.ProxyHandler({})
_OPENER = urllib.request.build_opener(_no_proxy_handler)


# ---- helpers ----

def _is_absolute_url(url):
    """判断 url 是否为绝对路径 (含 scheme)"""
    return bool(urlparse(url).scheme)


def _parse_version(v):
    """解析版本号 'x.y.z' → (x, y, z); 兼容 'v1.2.4'/'v1.3' 前缀; 空/非法返回 (0,)"""
    if not v:
        return (0,)
    s = str(v).strip()
    if s[:1].lower() == 'v':
        s = s[1:]
    parts = []
    for x in s.split('.'):
        try:
            parts.append(int(x))
        except ValueError:
            break
    return tuple(parts) or (0,)

# ---- exception ----

class PluginRepoError(Exception):
    """插件仓库操作异常"""


# ---- repository client ----

class PluginRepo:
    """远程插件仓库客户端

    所有网络操作均为静态方法, 方便在线程中调用
    """

    @staticmethod
    def fetch_index(url=None, app_type=None, app_version=None):
        """HTTP GET 获取插件列表 JSON, 并按当前软件过滤不兼容插件。

        *app_type*: 当前软件类型
        *app_version*: 当前软件版本号; 提供时按类型 + 最低版本兼容性过滤,
        类型不符或软件版本低于 min_app_version 的插件不会出现在结果中.
        """
        if url is None:
            url = REPO_INDEX_URL_DEFAULT
        if not url:
            raise PluginRepoError("未配置插件仓库 URL")

        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'UF-Toolbox-PluginStore/1.0',
            })
            with _OPENER.open(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.URLError as e:
            raise PluginRepoError(f"无法连接到插件仓库: {e}") from e
        except Exception as e:
            raise PluginRepoError(f"获取插件列表失败: {e}") from e

        try:
            data = json.loads(raw.decode('utf-8'))
        except json.JSONDecodeError as e:
            raise PluginRepoError(f"插件列表 JSON 解析失败: {e}") from e

        # 提取 base URL
        parsed = urlparse(url)
        base_path = os.path.dirname(parsed.path)
        base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}/"

        data['_base_url'] = base_url
        data.setdefault('plugins', [])
        if app_type or app_version:
            filtered = []
            for p in data['plugins']:
                # 外层 type 不兼容 → 直接跳过, 不遍历 versions
                if not PluginRepo._match_type(p, app_type):
                    continue
                resolved = PluginRepo.resolve_version(p, app_version)
                # 版本级 type 覆盖时以最终条目为准再判一次
                if resolved is not None and PluginRepo._match_type(resolved, app_type):
                    filtered.append(resolved)
            data['plugins'] = filtered
        return data

    @staticmethod
    def _match_type(pi, app_type):
        """类型判定: 无 type / '*' / app_type 兼容, 其余不兼容"""
        ptype = pi.get('type')
        return ptype in (None, '*', app_type)

    @staticmethod
    def resolve_version(pi, app_version):
        """解析插件在当前 app 下可安装的版本。

        多版本 (versions): 选择兼容 app_version 的最高版本, 将其
        version/url/size_kb/min_app_version/type/description 等字段
        提升到条目顶层并移除 versions; 版本条目缺省字段保留外层值。
        无兼容版本返回 None。app_version 为空时不做版本判定, 取最高版本。
        旧格式 (单版本): 按 min_app_version 判定, 兼容返回原条目, 否则 None。
        """
        versions = pi.get('versions')
        if versions:
            outer_min = pi.get('min_app_version')   # 默认门槛, 版本项缺省时回退
            if app_version:
                ok = [v for v in versions
                      if not v.get('min_app_version', outer_min)
                      or _parse_version(app_version)
                         >= _parse_version(v.get('min_app_version', outer_min))]
                if not ok:
                    return None
                best = max(ok, key=lambda v: _parse_version(v.get('version', '0')))
            else:
                best = max(versions, key=lambda v: _parse_version(v.get('version', '0')))
            out = dict(pi)
            out.pop('versions', None)
            # 版本条目可携带 type/description 等覆盖字段, 不存在则保留外层值
            for k in ('version', 'url', 'size_kb', 'min_app_version',
                      'type', 'description'):
                if k in best:
                    out[k] = best[k]
            return out
        min_ver = pi.get('min_app_version')
        if min_ver and app_version and _parse_version(app_version) < _parse_version(min_ver):
            return None
        return pi

    @staticmethod
    def is_compatible(pi, app_type, app_version):
        """远程插件条目是否与当前软件兼容: 存在任一兼容版本 + 最终类型匹配

        类型: 无 type / '*' / app_type 兼容, 其余过滤;
        版本: 多版本取兼容 app 的最高版本, 单版本按 min_app_version 判定.
        """
        resolved = PluginRepo.resolve_version(pi, app_version)
        return (resolved is not None
                and PluginRepo._match_type(resolved, app_type))

    @staticmethod
    def scan_installed(app):
        """扫描下载目标目录，返回已安装插件的信息"""
        install_dir = app.plugin_path
        result = {}
        if not os.path.isdir(install_dir):
            return result

        for entry in sorted(os.listdir(install_dir)):
            pkg_dir = os.path.join(install_dir, entry)
            if not os.path.isdir(pkg_dir) or entry.startswith('_'):
                continue
            if not os.path.isfile(os.path.join(pkg_dir, '__init__.py')):
                continue

            info_file = os.path.join(pkg_dir, STORE_INFO_FILE)
            if os.path.isfile(info_file):
                try:
                    with open(info_file, 'r', encoding='utf-8') as f:
                        result[entry] = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    result[entry] = {'version': None, 'source': 'store'}
            else:
                result[entry] = {'version': None, 'source': 'local'}

        return result

    @staticmethod
    def compare_status(installed_info, remote_info):
        """比较本地与远程版本，返回状态

        返回字符串:
            'install'   — 未安装
            'local'     — 本地自建插件 (无版本信息), 不可更新
            'update'    — 可更新
            'current'   — 已是最新版
            'orphan'    — 已安装但不在远程列表中
        """
        if installed_info is None:
            return 'install'
        if installed_info.get('source') == 'local':
            return 'local'
        installed_ver = installed_info.get('version')
        if installed_ver is None:
            return 'local'
        remote_ver = remote_info.get('version', '0')
        if _parse_version(installed_ver) < _parse_version(remote_ver):
            return 'update'
        return 'current'

    @staticmethod
    def download_and_install(url, base_url, target_dir, plugin_name,
                             version, author='', progress_callback=None):
        """后台线程：下载 ZIP → 临时目录解压 → 验证 → 移动到目标目录

        参数:
            url: 下载地址 (绝对路径直接使用, 相对路径拼接 base_url)
            base_url: 配置 JSON 所在目录 URL
            target_dir: 安装目标根目录
            plugin_name: 插件名称 (用作目标子目录名)
            version: 版本号
            author: 作者 (可选)
            progress_callback: 进度回调 callback(stage, percent)
                stage: 'downloading' | 'extracting' | 'done'

        任何步骤失败抛 PluginRepoError, 不会在 target_dir 留下半成品
        """
        # 解析完整 URL
        if _is_absolute_url(url):
            full_url = url
        else:
            full_url = urljoin(base_url, url)

        tmpdir = None
        try:
            tmpdir = tempfile.mkdtemp(prefix='uf_plugin_')
            zip_path = os.path.join(tmpdir, 'plugin.zip')

            # ---- 1. 下载 ----
            if progress_callback:
                progress_callback('downloading', 0)

            try:
                req = urllib.request.Request(full_url, headers={
                    'User-Agent': 'UF-Toolbox-PluginStore/1.0',
                })

                def _download_with_progress():
                    """带进度回调的下载"""
                    resp = _OPENER.open(req, timeout=TIMEOUT)
                    content_length = resp.headers.get('Content-Length')
                    total = int(content_length) if content_length else None
                    downloaded = 0
                    chunk_size = 8192
                    chunks = []
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            pct = min(int(downloaded / total * 100), 99)
                            progress_callback('downloading', pct)
                    resp.close()
                    return b''.join(chunks)

                data = _download_with_progress()
            except urllib.error.URLError as e:
                raise PluginRepoError(f"下载失败: {e}") from e

            if progress_callback:
                progress_callback('downloading', 100)

            # 写入临时 ZIP
            with open(zip_path, 'wb') as f:
                f.write(data)

            # ---- 2. 解压 ----
            if progress_callback:
                progress_callback('extracting', 0)

            extract_dir = os.path.join(tmpdir, 'extracted')
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)

            if progress_callback:
                progress_callback('extracting', 100)

            # ---- 3. 验证并确定插件源目录 ----
            extracted_items = os.listdir(extract_dir)

            # 过滤掉 MACOSX 等无关目录
            plugin_items = [x for x in extracted_items
                            if not x.startswith('__MACOSX')
                            and not x.startswith('.')]

            if not plugin_items:
                raise PluginRepoError("ZIP 包内没有有效内容")

            if len(plugin_items) == 1 and os.path.isdir(
                    os.path.join(extract_dir, plugin_items[0])):
                # ZIP 内只有一个顶层目录 → 直接使用
                src_dir = os.path.join(extract_dir, plugin_items[0])
            else:
                # 多个文件/目录 → 用 plugin_name 包裹
                src_dir = os.path.join(extract_dir, '__plugin_pkg__')
                os.makedirs(src_dir, exist_ok=True)
                for item in plugin_items:
                    shutil.move(os.path.join(extract_dir, item),
                                os.path.join(src_dir, item))

            # 验证：必须包含 __init__.py
            if not os.path.isfile(os.path.join(src_dir, '__init__.py')):
                raise PluginRepoError("ZIP 包内缺少 __init__.py, 不是有效的插件包")

            # ---- 4. 移动到目标目录 ----
            dest_dir = os.path.join(target_dir, plugin_name)
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
            shutil.move(src_dir, dest_dir)

            # ---- 5. 写入 .store_info.json ----
            info = {
                'version': version,
                'installed_at': datetime.now(timezone.utc).strftime(
                    '%Y-%m-%dT%H:%M:%SZ'),
                'url': url,
                'remote_name': plugin_name,
                'author': author,
            }
            info_path = os.path.join(dest_dir, STORE_INFO_FILE)
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info, f, ensure_ascii=False, indent=2)

            if progress_callback:
                progress_callback('done', 100)

        except PluginRepoError:
            raise
        except Exception as e:
            raise PluginRepoError(f"安装失败: {e}") from e
        finally:
            # ---- 6. 清理临时目录 ----
            if tmpdir and os.path.isdir(tmpdir):
                try:
                    shutil.rmtree(tmpdir)
                except OSError:
                    pass
