# -*- coding: utf-8 -*-
"""OpenAI-compatible chat client — urllib only, no third-party deps.

Streaming chat completions with tool-call delta accumulation.  Works with
any OpenAI-compatible endpoint (DeepSeek, Claude-compatible gateways, ...).
UI-independent: errors are raised as LLMError with a user-displayable
message; the caller shows them.
"""
import json
import urllib.error
import urllib.request


class LLMError(Exception):
    """API/网络错误 — str(e) 可直接展示给用户."""


def list_detected_proxies():
    """系统检测到的全部代理地址 (环境变量 + Windows 注册表), 去重保序."""
    seen = []
    for v in urllib.request.getproxies().values():
        if v and v not in seen:
            seen.append(v)
    return seen


class OpenAIClient:
    """Minimal streaming chat client (OpenAI-compatible API)."""

    def __init__(self, base_url, api_key, model, timeout=180, proxy='system'):
        """proxy: 'system'=走系统代理(urllib默认); 'none'=直连;
        'http://host:port'=显式代理。国内端点(DeepSeek/Kimi等)建议
        'none' — 异常的系统代理(如本地翻墙工具)会把 TTFT 拉高十几秒。
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.last_usage = None   # 最近一次请求的 usage (服务端计量, 可能为 None)
        if proxy == 'none':
            self._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}))
        elif proxy and proxy != 'system':
            self._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
        else:
            self._opener = urllib.request.build_opener()

    def chat_stream(self, messages, tools=None):
        """Yield ``(delta_text, tool_call_deltas)`` per SSE chunk.

        tool_call_deltas: list of dicts ``{index, id, name, arguments}`` —
        id/name/arguments may arrive as partial fragments across chunks,
        the caller accumulates them by index (standard OpenAI streaming
        behaviour).

        请求带 ``stream_options.include_usage`` — 兼容端点会在最后一个
        chunk 返回 usage, 解析后存入 ``self.last_usage``。
        """
        payload = {'model': self.model, 'messages': messages, 'stream': True,
                   'stream_options': {'include_usage': True}}
        if tools:
            payload['tools'] = tools
        self.last_usage = None
        for _attempt in range(2):
            try:
                resp = self._open(payload)
                break
            except urllib.error.HTTPError as e:
                body = e.read(512).decode('utf-8', errors='replace')
                # 部分兼容端点不支持 stream_options — 400 时去掉重试一次
                # (last_usage 退化为 None, 属可接受降级)
                if e.code == 400 and payload.pop('stream_options', None):
                    continue
                raise LLMError('HTTP %s: %s' % (e.code, body)) from e
            except (urllib.error.URLError, OSError) as e:
                raise self._net_error(e) from e
        with resp:
            for line in resp:
                line = line.decode('utf-8', errors='replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    return
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                # 流中途的业务错误 (限流/上下文超长等) 以 error 字段下发,
                # 无 choices — 不检测会被静默吞掉, 表现为"回复为空无报错"
                err = chunk.get('error')
                if err:
                    msg = err.get('message') if isinstance(err, dict) \
                        else str(err)
                    raise LLMError('stream error: %s' % msg)
                if chunk.get('usage'):
                    self.last_usage = self._normalize_usage(chunk['usage'])
                choices = chunk.get('choices') or []
                if not choices:
                    continue
                delta = choices[0].get('delta') or {}
                text = delta.get('content') or ''
                tc = []
                for t in delta.get('tool_calls') or []:
                    fn = t.get('function') or {}
                    tc.append({'index': t.get('index', 0),
                               'id': t.get('id'),
                               'name': fn.get('name'),
                               'arguments': fn.get('arguments')})
                yield text, tc

    @staticmethod
    def _normalize_usage(usage):
        """各家 usage 字段 → 追加统一平铺键 cache_hit / cache_miss.

        DeepSeek 平铺给 prompt_cache_hit/miss_tokens; OpenAI/Moonshot
        缓存在嵌套 prompt_tokens_details.cached_tokens。提升到顶层后
        下游多轮累加 (只认顶层数值键) 与面板显示都无需关心 provider
        差异; 原始键保留不动。端点完全未报缓存信息时两键为 0
        (miss 不做推算 — 否则面板会对无缓存端点误显示拆分)。
        """
        hit = (usage.get('prompt_cache_hit_tokens')
               or (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
               or usage.get('cached_tokens'))
        miss = usage.get('prompt_cache_miss_tokens')
        if hit is None and miss is None:
            usage['cache_hit'] = 0
            usage['cache_miss'] = 0
        else:
            usage['cache_hit'] = hit or 0
            usage['cache_miss'] = miss if miss is not None \
                else usage.get('prompt_tokens', 0) - usage['cache_hit']
        return usage

    def _open(self, payload):
        """构造请求并打开流式响应 (异常抛给调用方分类).

        ensure_ascii=False: 默认 True 会把中文转义为 \\uXXXX (3→6 字节/字),
        中文对话 payload 上传体积膨胀近 2 倍。
        Accept-Encoding: identity: 防御个别网关在流式响应上开 gzip
        (urllib 不会自动解压, SSE 解析会全挂)。
        """
        req = urllib.request.Request(
            self.base_url + '/chat/completions',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer ' + self.api_key,
                     'Accept-Encoding': 'identity'},
            method='POST')
        return self._opener.open(req, timeout=self.timeout)

    def _net_error(self, e):
        """URLError/OSError → 用户可读的 LLMError."""
        reason = getattr(e, 'reason', e)
        if isinstance(reason, TimeoutError) or 'timed out' in str(reason):
            return LLMError(
                '请求超时 (当前 %ss, 可在 agent_config.json 调大 timeout)'
                % self.timeout)
        return LLMError('network error: %s' % e)
