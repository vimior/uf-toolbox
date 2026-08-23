import os
import re
import uuid
import json
from dataclasses import dataclass

CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.uf_toolbox', 'agent')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'agent_config.json')


def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default

# ---------------------------------------------------------------------------
# API key 自动匹配 — 按端点选择来源, 只在端点匹配时才取对应 key
# ---------------------------------------------------------------------------
# 端点特征 → (环境变量, 配置文件来源); 顺序即匹配顺序
_ENV_KEYS = (
    ('deepseek', 'DEEPSEEK_API_KEY'),
    ('openai', 'OPENAI_API_KEY'),
    ('claude', 'ANTHROPIC_API_KEY'),
    ('moonshot', 'MOONSHOT_API_KEY'),
    ('kimi', 'KIMI_API_KEY'),
    ('bigmodel', 'ZHIPUAI_API_KEY'),
)

def find_api_key(url):
    """
    按端点自动匹配 API key, 返回 (key, source).
    
    source: 'env' / 'claude' / 'codex' / ''。端点不识别时不匹配 —
    避免把 deepseek 的 key 误发给其他端点。
    """
    host = str(url or '').lower()
    for feature, var in _ENV_KEYS:
        if feature not in host:
            continue
        key = os.environ.get(var, '').strip()
        if key:
            return key, 'env'
        if feature == 'openai':
            key = _get_key_from_codex()
            if key:
                return key, 'system'
        elif feature == 'claude':
            key = _get_key_from_claude()
            if key:
                return key, 'system'
        else:
            key = _get_key_from_claude(provider=feature)
            if key:
                return key, 'claude'
            key = _get_key_from_codex(provider=feature)
            if key:
                return key, 'codex'
        break
    return '', ''

def _get_key_from_claude(provider='claude'):
    """从 Claude Code 的配置文件获取指定服务商(provider)的API_KEY."""
    try:
        with open(os.path.join(os.path.expanduser('~'), '.claude',
                            'settings.json'), encoding='utf-8') as f:
            data = json.load(f)
        env = data.get('env') or {}
        if provider in ('anthropic', 'claude'):
            key = str(env.get('ANTHROPIC_API_KEY') or '').strip()
            return key
        else:
            key = str(env.get('ANTHROPIC_AUTH_TOKEN') or '').strip()
            base = str(env.get('ANTHROPIC_BASE_URL') or '').lower()
            if key and provider in base:
                return key
    except (OSError, ValueError, AttributeError):
        pass
    return ''

def _get_key_from_codex(provider='codex'):
    """从 Codex 的配置文件获取指定服务商(provider)的API_KEY."""
    try:
        if provider in ('openai', 'codex'):
            with open(os.path.join(os.path.expanduser('~'), '.codex',
                                    'auth.json'), encoding='utf-8') as f:
                data = json.load(f)
            key = str(data.get('OPENAI_API_KEY') or '').strip()
            return key
        else:
            path = os.path.join(os.path.expanduser('~'), '.codex', 'config.toml')
            try:
                with open(path, encoding='utf-8') as f:
                    lines = f.read().splitlines()
            except OSError:
                return ''
            section = ''
            provider_section = None
            for line in lines:
                s = line.strip()
                if s.startswith('['):
                    section = s
                elif provider_section is None and f'"{provider}"' in s and 'name' in s:
                    provider_section = section
            if provider_section is None:
                return ''
            section = ''
            for line in lines:
                s = line.strip()
                if s.startswith('['):
                    section = s
                elif section == provider_section:
                    m = re.match(r'^(?:experimental_)?(?:bearer_token|auth_token|api_key)'
                                    r'\s*=\s*["\']([^"\']+)["\']', s)
                    if m:
                        return m.group(1).strip()
    except (OSError, ValueError, AttributeError):
        pass
    return ''


class Config:
    _instance = None
    _DEFAULT_CONFIG = {
        'id': 'internal@deepseek',
        'model': 'deepseek-chat',
        'timeout': 180,      # socket 读超时 (秒) — 推理模型思考期可能长时间无输出
        'proxy': 'system',   # system=系统代理 / none=直连(国内端点推荐) / http://host:port
    }
    # 预设端点条目: {'id', 'name', 'url', 'api_key', 'models'} — 面板下拉与设置窗口共享
    _DEFAULT_PROVIDERS = [
        {'id': 'internal@deepseek', 'name': 'DeepSeek', 'url': 'https://api.deepseek.com/v1', 'api_key': '', 'models': ['deepseek-chat', 'deepseek-reasoner', 'deepseek-v4-pro', 'deepseek-v4-flash']},
        {'id': 'internal@openai', 'name': 'OpenAI', 'url': 'https://api.openai.com/v1', 'api_key': '', 'models': ['gpt-4o', 'gpt-4o-mini', 'o3-mini', 'gpt-4-turbo', 'gpt-3.5-turbo']},
        {'id': 'internal@moonshot', 'name': 'Moonshot', 'url': 'https://api.moonshot.cn/v1', 'api_key': '', 'models': ['moonshot-v1-128k', 'moonshot-v1-32k', 'moonshot-v1-8k']},
        {'id': 'internal@kimi', 'name': 'Kimi', 'url': 'https://api.kimi.com/coding/v1', 'api_key': '', 'models': ['kimi-k3', 'kimi-k2.7-code', 'kimi-k2.7-code-highspeed', 'kimi-k2.6', 'kimi-k2.5']},
        {'id': 'internal@glm', 'name': 'GLM', 'url': 'https://open.bigmodel.cn/api/paas/v4', 'api_key': '', 'models': ['glm-5.2', 'glm-5.1', 'glm-5', 'glm-5-turbo', 'glm-5v-turbo', 'glm-4-plus']},
        {'id': 'internal@gemini', 'name': 'Gemini', 'url': 'https://generativelanguage.googleapis.com/v1beta/openai', 'api_key': '', 'models': ['gemini-3.5-flash', 'gemini-3.5-flash-8b', 'gemini-2.0-flash']},
        {'id': 'internal@grok', 'name': 'Grok', 'url': 'https://api.x.ai/v1', 'api_key': '', 'models': ['grok-4.6', 'grok-4.5', 'grok-4.3']},
        # {'id': 'internal@qwen', 'name': 'Qwen', 'url': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'api_key': ''},
        # {'id': 'internal@minimax', 'name': 'MiniMax', 'url': 'https://api.minimax.chat/v1', 'api_key': ''},
        # {'id': 'internal@hunyuan', 'name': '腾讯混元', 'url': 'https://api.hunyuan.cloud.tencent.com/v1', 'api_key': ''},
        # {'id': 'internal@baidubce', 'name': '百度千帆', 'url': 'https://qianfan.baidubce.com/v2', 'api_key': ''},
        # {'id': 'internal@lingyiwanwu', 'name': '零一万物', 'url': 'https://api.lingyiwanwu.com/v1', 'api_key': ''},
        # {'id': 'internal@baichuan', 'name': '百川智能', 'url': 'https://api.baichuan-ai.com/v1', 'api_key': ''},
        # {'id': 'internal@stepfun', 'name': '阶跃星辰', 'url': 'https://api.stepfun.com/v1', 'api_key': ''},
    ]
    DEFAULT_PROVIDERS = []

    @dataclass
    class Current:
        model: str = ''
        timeout: float = 180
        proxy: str = 'system'

        def __init__(self, *args, **kwargs):
            self._api_key = ''
            self._key_source = ''
            self._provider = {}
            self.model = args[0] if len(args) > 0 else kwargs.get('model', self.model)
            timeout = args[1] if len(args) > 1 else kwargs.get('timeout', self.timeout)
            self.set_timeout(timeout)
            self.proxy = args[2] if len(args) > 2 else kwargs.get('proxy', self.proxy)

        def set_provider(self, provider):
            if not provider.get('models', []):
                return False
            if not self._provider:
                self._provider = provider
                if self.model not in provider['models']:
                    self.model = provider['models'][0]
                self._api_key = provider.get('api_key', '')
                if not self._api_key:
                    self._api_key, self._key_source = find_api_key(provider['url'])
                else:
                    self._key_source = 'config'
                return True
            if self.model not in provider['models']:
                self.model = provider['models'][0]
            if provider['id'] == self._provider['id'] and self._provider['url'] == provider['url']:
                if provider['api_key']:
                    self._api_key = provider['api_key']
                    self._key_source = 'config'
                else:
                    if not self._api_key:
                        self._api_key, self._key_source = find_api_key(provider['url'])
            else:
                self._api_key = provider['api_key']
                if self._api_key:
                    self._key_source = 'config'
                else:
                    self._api_key, self._key_source = find_api_key(provider['url'])
            self._provider = provider
            return True

        def get_provider(self):
            return self._provider

        def set_model(self, model):
            if not self._provider:
                return False
            if model not in self._provider.get('models', []):
                return False
            self.model = model
            return True

        def set_timeout(self, timeout):
            try:
                timeout = float(timeout)
                if timeout == self.timeout:
                    return False
                self.timeout = timeout
                return True
            except:
                return False

        def set_proxy(self, proxy):
            if not proxy or proxy == self.proxy:
                return False
            self.proxy = proxy
            return True

        def to_dict(self):
            return {
                'id': self._provider.get('id', ''),
                'url': self._provider.get('url', ''),
                'models': self._provider.get('models', []),
                'model': self.model,
                'api_key': self._api_key,
                'key_source': self._key_source,
                'timeout': self.timeout,
                'proxy': self.proxy,
            }

    def __init__(self):
        # 内置自检, 排除掉哪些没有ID或者没有models或者name重复的
        seens = set()
        for provider in self._DEFAULT_PROVIDERS:
            if 'id' not in provider or 'models' not in provider or len(provider['models']) == 0:
                continue
            if provider['name'] in seens:
                continue
            seens.add(provider['name'])
            self.DEFAULT_PROVIDERS.append(provider)
        self._config, self._current, self._config_str = self.reload()

    def reload(self):
        cfg = self._load()
        providers = cfg['providers']
        curr_id = cfg.get('id', '')
        curr_privider = providers[0] if not curr_id else {}
        for provider in cfg['providers']:
            if curr_privider:
                break
            if provider['id'] == curr_id:
                curr_privider = provider
                break
        if not curr_privider:
            curr_privider = providers[0]
            cfg['id'] = curr_privider['id']
        current = self.Current(
            model=cfg.get('model', ''),
            timeout=cfg.get('timeout', 180),
            proxy=cfg.get('timeout', 'system'),
        )
        current.set_provider(curr_privider)
        try:
            config_str = json.dumps(cfg)
        except:
            config_str = ''
        self._config, self._current, self._config_str = cfg, current, config_str
        
        return cfg, current, config_str

    @property
    def current(self):
        return self._current.to_dict()

    def set_providers(self, providers=None):
        if not providers or not isinstance(providers, list):
            return self._config.get('providers', [])
        # 过滤不合规范的
        providers = [p for p in providers if self._check_provider(p)]
        self._config['providers'] = providers
        curr_provider_id = self.current['id']
        curr_provider = providers[0]
        for provider in providers:
            if curr_provider_id != provider['id'] or not provider['models']:
                continue
            curr_provider = provider
            break
        self.set_current_provider(curr_provider)
        return providers

    def get_current_provider(self):
        return self._current.get_provider()

    def set_current_provider(self, provider):
        self._current.set_provider(provider)
        self._config['id'] = self.current['id']
        self._config['model'] = self.current['model']
        self._save()
        return True

    def set_current_model(self, model):
        if self._current.set_model(model):
            self._config['model'] = model
            self._save()
            return True
        return False

    def set_proxy(self, proxy):
        if self._current.set_proxy(proxy):
            self._config['proxy'] = proxy
            self._save()
            return True
        return False

    @property
    def providers(self):
        return self._config['providers']

    def _load(self):
        cfg = dict(self._DEFAULT_CONFIG)
        cfg.update(load_json(CONFIG_PATH, {}))
        providers = cfg.get('providers', [])
        cfg['providers'] = [dict(p, models=list(p.get('models', []))) for p in self.DEFAULT_PROVIDERS]
        if not isinstance(providers, list):
            providers = []
        seens = set([p['name'] for p in self.DEFAULT_PROVIDERS])
        for provider in providers:
            if not self._check_provider(provider):
                # 排除不合规范的
                continue
            inx = self._is_internal_provider(provider)
            if inx >= 0:
                # 内置的, 更新部分信息
                cfg['providers'][inx]['api_key'] = provider['api_key']
                if provider.get('models', []):
                    # 如果models不为空，就更新models为对应的配置provider的models
                    cfg['providers'][inx]['models'] = provider['models']
            else:
                if provider['name'] in seens:
                    # 排除name重复的
                    continue
                seens.add(provider['name'])
                # 自定义的, 追加进配置
                cfg['providers'].append(provider)
    
        curr_id = cfg.get('id', '')
        curr_model = cfg.get('model', '')
    
        default_provider = cfg['providers'][0]
        cfg['id'] = default_provider['id']
        cfg['model'] = default_provider['models'][0]
    
        if not curr_id:
            return cfg
    
        for provider in cfg['providers']:
            if curr_id != provider['id'] or not provider['models']:
                continue
            # curr_id和provider的id匹配上
            cfg['id'] = provider['id']
            cfg['model'] = provider['models'][0]
            for model in provider['models']:
                if curr_model != model:
                    continue
                cfg['model'] = model
                break
            break
        return cfg

    def _save(self):
        if not self._config:
            return False
        try:
            json_str = json.dumps(self._config)
            if json_str == self._config_str:
                return False
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, ensure_ascii=False, indent=2)
            self._config_str = json_str
            return True
        except Exception as e:
            print('save error:', e)
            return False

    @staticmethod
    def _check_provider(provider):
        if not provider or not isinstance(provider, dict):
            return False
        name = provider.get('name', '')
        url = provider.get('url', '')
        if not isinstance(name, str) or not isinstance(url, str):
            return False
        name, url = name.strip(), url.strip()
        if not name or not url:
            return False
        provider['name'] = name
        provider['url'] = url
        if not provider.get('id', ''):
            # 补上缺失的id
            provider['id'] = uuid.uuid4().hex
        if 'api_key' not in provider:
            # 补上缺失的api_key字段, 默认为空
            provider['api_key'] = ''
        if 'models' not in provider:
            # 补上缺失的models
            provider['models'] = []
        models = provider['models']
        if not isinstance(models, (tuple, list)):
            provider['models'] = []
        else:
            models = [str(model).strip() for model in models]
            provider['models'] = models
        return True

    def _is_internal_provider(self, provider):
        """
        判断是否是内置的, 是就返回索引, 否则返回-1
        轮询DEFAULT_PROVIDERS, id/name/url都一样则判定为内置的
        """
        for i, p in enumerate(self.DEFAULT_PROVIDERS):
            if p.get('id', '') == provider['id'] and p.get('name') == provider['name'] and p.get('url') == provider['url']:
                return i
        return -1
