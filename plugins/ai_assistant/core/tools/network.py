# -*- coding: utf-8 -*-
"""网络工具 — http_request / ping_host (+ 面板摘要).

模块级函数 + register(reg) 显式注册 (无 import 副作用);
签名即 schema (@reg.tool 自动推导)。
"""
import platform
import re
import subprocess
import urllib.error
import urllib.request

_MAX_BODY = 64 * 1024   # 工具返回体截断上限 (同 http tab)


def http_request(url: str, method: str = 'GET',
                 headers: str = '', body: str = '') -> str:
    """用户明确要求发送 HTTP 请求或访问某 URL 时使用; 不要在其他任务中主动调用。
    url: URL, http:// 可省略
    method: GET/POST/PUT/DELETE...
    headers: 每行一条 Key: Value
    body: 请求体"""
    url = str(url or '').strip()
    if not url:
        return 'empty url'
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    method = str(method or 'GET').upper()
    data = body.encode('utf-8') if (method != 'GET' and body) else None
    req_headers = {}
    for line in str(headers or '').splitlines():
        if ':' in line:
            k, v = line.split(':', 1)
            req_headers[k.strip()] = v.strip()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            resp_headers = str(resp.headers)
            content = resp.read(_MAX_BODY + 1)
        truncated = len(content) > _MAX_BODY
        content = content[:_MAX_BODY]
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('gbk', errors='replace')
        out = 'HTTP %s\n%s\n\n%s' % (status, resp_headers, text)
        if truncated:
            out += '\n(truncated)'
        return out
    except urllib.error.HTTPError as e:
        return 'HTTP %s %s\n%s' % (e.code, e.reason,
                                   e.read(512).decode('utf-8', errors='replace'))
    except (urllib.error.URLError, OSError) as e:
        return 'request error: %s' % e


def ping_host(host: str, count: int = 4) -> str:
    """用户明确要求检测网络连通性时使用; 不要在其他任务中主动调用。
    host: 主机名或 IP
    count: 次数, 默认 4"""
    host = str(host or '').strip()
    if not host:
        return 'empty host'
    count = int(count)
    is_win = platform.system().lower() == 'windows'
    if is_win:
        cmd = ['ping', '-n', str(count), '-w', '2000', host]
    else:
        cmd = ['ping', '-c', str(count), '-W', '2', host]
    try:
        out = subprocess.run(cmd, capture_output=True,
                             timeout=count * 3 + 5)
        raw = out.stdout or out.stderr
        return raw.decode('gbk' if is_win else 'utf-8', errors='replace')
    except subprocess.TimeoutExpired:
        return 'ping timeout'
    except OSError as e:
        return 'ping error: %s' % e


# ---------------------------------------------------------------------------
# 面板摘要 (summary) — 一行展示用, 解析失败返回 None 由面板回退截取
# ---------------------------------------------------------------------------


def _ping_summary(result, args=None):
    """摘要如 '8.8.8.8: 丢包 0% (4/4), 平均 24ms' — 兼容中英/Windows/Linux.

    目标主机优先取 args['host'], 缺失时从结果中提取; 解析失败返回 None。
    """
    host = ''
    if isinstance(args, dict) and args.get('host'):
        host = str(args['host']).strip()
    else:
        m = re.search(r'(?:正在 Ping|PING)\s+(\S+)', result)
        if m:
            host = m.group(1)
    if host:
        host += ': '
    # 丢包数: '丢失 = 0' / 'Lost = 0' / '0% packet loss'
    m = re.search(r'(?:丢失|Lost)\s*=\s*(\d+)', result)
    loss_n = int(m.group(1)) if m else None
    if loss_n is None:
        m = re.search(r'(\d+)\s*%\s*(?:packet\s+)?loss', result)
        if m:
            loss_n = int(m.group(1))
    # 收发包数: '已发送 = 4，已接收 = 4' / 'Sent = 4, Received = 4' /
    #          '4 packets transmitted, 4 received'
    m = re.search(r'(?:已接收|Received)\s*=\s*(\d+)', result)
    recv = int(m.group(1)) if m else None
    m = re.search(r'(\d+)\s*packets transmitted,\s*(\d+)\s*received', result)
    if recv is None and m:
        recv = int(m.group(2))
    sent = None
    m = re.search(r'(?:已发送|Sent)\s*=\s*(\d+)', result)
    if m:
        sent = int(m.group(1))
    elif recv is not None and loss_n is not None:
        sent = recv + loss_n
    # 平均延迟: '平均 = 24ms' / 'Average = 24ms' / 'min/avg/max = 23/24/25'
    avg = None
    m = re.search(r'(?:平均|Average)\s*=\s*(\d+)\s*ms', result)
    if m:
        avg = m.group(1)
    else:
        m = re.search(r'min/avg/max.*?=\s*[\d.]+\s*/\s*([\d.]+)', result)
        if m:
            avg = m.group(1)
    if loss_n is None and avg is None:
        return None
    parts = []
    if loss_n is not None:
        parts.append('丢包 %d%%%s' % (loss_n,
                    (' (%d/%d)' % (recv, sent))
                    if recv is not None and sent is not None else ''))
    if avg is not None:
        parts.append('平均 %sms' % avg)
    return (host + ', '.join(parts)) if parts else None


def _http_summary(result, args=None):
    """摘要如 'GET http://x/api: HTTP 200 (4.2 KB)'. 非 HTTP 结果返回 None.

    目标 (method + url) 取自 args, 面板不直接显示参数 JSON。
    """
    first = (result or '').splitlines()[0].strip() if result else ''
    if not first.startswith('HTTP '):
        return None
    target = ''
    if isinstance(args, dict) and args.get('url'):
        method = str(args.get('method') or 'GET').upper()
        target = '%s %s: ' % (method, str(args['url']).strip())
    body = result.split('\n\n', 1)[-1] if '\n\n' in result else ''
    truncated = body.endswith('\n(truncated)')
    body = body[:len(body) - len('\n(truncated)')] if truncated else body
    kb = len(body.encode('utf-8', errors='replace')) / 1024.0
    size = ('%.1f KB' % kb) if kb >= 1 else ('%d B' % len(body))
    if truncated:
        size += '+'
    return '%s%s (%s)' % (target, first, size)


def register(reg):
    """把本模块工具注册进给定注册表 (幂等)."""
    reg.tool(summary=_http_summary)(http_request)
    reg.tool(summary=_ping_summary)(ping_host)
