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

# 禁用系统代理检测（避免 Windows WPAD 造成 10+ 秒延迟）
_no_proxy_handler = urllib.request.ProxyHandler({})
_OPENER = urllib.request.build_opener(_no_proxy_handler)


# ---- helpers ----

def _resolve_install_dir(app):
    """返回插件下载的目标目录。

    开发环境（.py / .pyw 入口）：
        <项目根>/dist/<plugin_path>
    打包环境（.exe 入口）：
        <exe 所在目录>/<plugin_path>
    """
    plugin_path = app.plugin_path
    exe_ext = os.path.splitext(sys.argv[0])[1].lower()


    if exe_ext not in ('.py', '.pyw'):
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', '..', 'dist')

    result = os.path.join(base, plugin_path)
    return result


def _is_absolute_url(url):
    """判断 url 是否为绝对路径（含 scheme）。"""
    return bool(urlparse(url).scheme)


# ---- exception ----

class PluginRepoError(Exception):
    """插件仓库操作异常。"""


# ---- repository client ----

class PluginRepo:
    """远程插件仓库客户端。

    所有网络操作均为静态方法，方便在线程中调用。
    """

    @staticmethod
    def fetch_index(url=None):
        """HTTP GET 获取插件列表 JSON。"""
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
        return data

    @staticmethod
    def scan_installed(app):
        """扫描下载目标目录，返回已安装插件的信息。"""
        install_dir = _resolve_install_dir(app)
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
        """比较本地与远程版本，返回状态。

        返回字符串:
            'install'   — 未安装
            'local'     — 本地自建插件（无版本信息），不可更新
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
        iv = tuple(int(x) for x in installed_ver.split('.'))
        rv = tuple(int(x) for x in remote_ver.split('.'))
        if iv < rv:
            return 'update'
        return 'current'

    @staticmethod
    def download_and_install(url, base_url, target_dir, plugin_name,
                             version, author='', progress_callback=None):
        """后台线程：下载 ZIP → 临时目录解压 → 验证 → 移动到目标目录。

        参数:
            url: 下载地址（绝对路径直接使用，相对路径拼接 base_url）
            base_url: 配置 JSON 所在目录 URL
            target_dir: 安装目标根目录
            plugin_name: 插件名称（用作目标子目录名）
            version: 版本号
            author: 作者（可选）
            progress_callback: 进度回调 callback(stage, percent)
                stage: 'downloading' | 'extracting' | 'done'

        任何步骤失败抛 PluginRepoError，不会在 target_dir 留下半成品。
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
                    """带进度回调的下载。"""
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
                raise PluginRepoError("ZIP 包内缺少 __init__.py，不是有效的插件包")

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
