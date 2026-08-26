# -*- coding: utf-8 -*-
"""AgentService — 后台 agent 服务 (ServicePlugin, 无 UI).

服务接口 (agent@): ask / stop / clear_session / list_tools /
confirm_result / register_tool / reload_config
事件 (agent@): chunk / tool_call / tool_result / done / error
store (agent@): status (busy|idle)

线程模型 (同 notify_service): agent 工作线程 → 事件队列 →
event_generate('<<AgentPoll>>') 唤醒主线程 drain → 主线程 emit 事件。
确认握手: 工作线程 Event 等待, 主线程弹窗后 confirm_result 回传。
会话/配置持久化在服务侧 — 面板关闭不丢会话。

本类不从包 __init__ 导出 — 由 manager 的 BUILTIN_SERVICES
内置启动 (同 task_service), 随 uf-tool 启动运行。
"""
import json
import os
import queue
import threading

from plugins.plugin import ServicePlugin

from .config import Config, load_json, CONFIG_DIR
from .core.agent import Agent
from .core.basic_qa import match_basic_qa
from .core.llm import LLMError, OpenAIClient
from .core.local_intent import extract_open
from .core.registry import registry
from .core.schema import make_schema

_SESSION_PATH = os.path.join(CONFIG_DIR, 'agent_session.json')
_MAX_SESSION_MSGS = 24   # 会话历史上限 (含工具交换 ≈ 5 轮问答), 超限自动截断

# 行为约束 — 防止模型重做历史任务/调用无关工具 (弱模型的常见热身行为)
_SYSTEM_PROMPT = """\
## TOOL_PROMPT: plugins_operation / tools_operation 调度规范

### 执行流程: 拆解 → 分类 → 执行

---

#### 一、拆解
将用户请求拆分为独立子任务,每个子任务包含:
- 操作类型(打开(启动)|关闭(停止)|隐藏...)
- 目标对象(名称或描述)

多请求必须逐条拆分,禁止合并处理。

---

#### 二、分类(对每个子任务独立判断)

**前置约束:**
- plugins列表只有在用到且不在上下文和缓存中时才获取
- 已获取的列表在后续子任务中复用,禁止重复调用

**规则A: 操作 = "打开"**
. 先在plugins列表中匹配
. 若精准匹配(名称完全相同) → 归入【插件类】,结束
. 若未精准匹配,如果tools列表不在上下文或者缓存,先获取tools列表,然后在plugins列表和tools列表中同时搜索,按以下优先级取最佳候选:
   a) 名称完全相同(精确匹配)
   b) 名称包含关系(如"网络工具"匹配"网络工具集合")
   c) 语义最相近(如"清理垃圾"匹配"磁盘清理")
. 取匹配度最高的候选项,按其来源列表归入【插件类】或【工具类】
. 若最佳匹配明显牵强(仅单字重合/完全无关) → 标记【不可执行】

**规则B: 操作 ≠ "打开"**
. 仅在plugins列表中匹配
. 匹配成功 → 归入【插件类】
. 匹配失败 → 标记【不可执行】

---

#### 三、执行
- 【插件类】→ 调用 plugins_operation(对应操作, 目标)
- 【工具类】→ 调用 tools_operation(对应操作, 目标)
- 【不可执行】→ 告知用户无法执行并说明原因

---

#### 四、总结
- 执行完毕后统一回复,逐项列出"✅成功 / ❌失败(附原因) / ⚠️不可执行(缺什么能力)"
- 每项≤1句,不复述操作细节,不延伸建议

---

### 禁止事项
- 禁止跳过拆解直接执行多目标请求
- 禁止在未获取列表时凭空猜测分类
- 禁止将规则B的操作(非打开)路由到tools列表
- 禁止在列表已存在于上下文时重复获取
- 禁止主动重试历史失败操作
- 非必需工具不调用,参数只传必需项
"""


class AgentService(ServicePlugin):
    name = "U-Bot Service"
    name_zh = "小U 服务"
    name_en = "U-Bot Service"
    namespace = "agent"
    auto_start = True       # 迁移内置后随 uf-tool 启动
    priority = 100

    def __init__(self, app=None):
        super().__init__(app)
        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._task_seq = 0
        self._stops = {}        # task_id -> threading.Event
        self._confirms = {}     # task_id -> {'event', 'result'}
        self._busy = 0
        self._running = True
        self._config = Config()
        # 设置到软件app里面，这样插件就可以共用同一个config实例了
        setattr(self.app._app, 'agent_config', self._config)
        self._session = self._load_session()
        self._win = self.root

    # ---- 生命周期 ----

    def on_start(self):
        self.services.register('ask', self._svc_ask)
        self.services.register('stop', self._svc_stop)
        self.services.register('clear_session', self._svc_clear_session)
        self.services.register('get_session', self._svc_get_session)
        self.services.register('list_tools', self._svc_list_tools)
        self.services.register('confirm_result', self._svc_confirm_result)
        self.services.register('register_tool', self._svc_register_tool)
        self.root.bind('<<AgentPoll>>', self._on_poll)
        self.store.commit('status', 'idle')
        # 内置 6 工具 (core/tools/) 暂不注册 — 垂直场景价值低, 通用能力
        # 由插件承接; 恢复: 重新 import register_builtin 并在此调用 (幂等)
        self._load_declared_tools()

    def _load_declared_tools(self):
        """从 manager 拉取全部插件的 agent_tools 声明建注册表 (不执行插件代码).

        manager 经 AST 扫描已获知各插件声明; 能力执行时才懒启动插件.
        """
        try:
            caps = self.services.call('plugins@list_capabilities')
        except KeyError:
            return
        for entry in caps or []:
            for name, spec in (entry.get('tools') or {}).items():
                if not isinstance(spec, dict):
                    continue
                ref = spec.get('fn_ref') or ''
                if '@' not in ref:
                    continue
                schema = make_schema(name, spec.get('description', ''),
                                      spec.get('params') or [])
                registry.register(name, spec.get('description', ''), schema,
                                  fn_ref=ref,
                                  dangerous=bool(spec.get('dangerous')))

    def on_stop(self):
        self._running = False
        for ev in list(self._stops.values()):
            ev.set()
        for c in list(self._confirms.values()):
            c['event'].set()    # 释放等待中的工作线程
        try:
            self.root.unbind('<<AgentPoll>>')
        except Exception:
            pass

    # ---- 服务接口 (面板/其他插件/定时任务调用) ----

    def _svc_ask(self, question, carry=True, win=None, local_first=True):
        """发起提问 — 立即返回 task_id, 结果经 agent@* 事件流推送.

        carry=False 单轮问答: 只发当前问题, 不读不写会话历史。
        """
        if not isinstance(question, str) or not question.strip():
            return -1
        with self._lock:
            self._task_seq += 1
            task_id = self._task_seq
        # 内置基础问答 — 本地应答, 不走 LLM (不消耗 token, 不写会话)
        answer = match_basic_qa(question,
                                [t['name'] for t in registry.list_tools()])
        if answer is not None:
            if '\n' in answer:
                # 多行 (skills) 走 chunk → 面板 markdown 渲染
                self._q_put(('chunk', task_id, answer))
            else:
                # 单行 (唤醒/问候等) → 面板内联接在 "Agent: " 后
                self._q_put(('local', task_id, answer))
            # 第 4 元素 'local' 哨兵 → 面板跳过 tokens 行与总耗时显示
            self._q_put(('done', task_id, answer, 'local'))
            return task_id
        # 本地意图 (打开/关闭类指令) — 唯一命中直执, 未命中静默交 LLM
        if local_first and self._try_local_intent(task_id, question, carry):
            return task_id
        if not self._config.current['api_key'].strip():
            return -2
        with self._lock:
            stop = threading.Event()
            self._stops[task_id] = stop
        self._set_status(self._busy + 1)
        self._win = win if win else self.root
        threading.Thread(target=self._worker,
                         args=(task_id, question, stop, carry),
                         daemon=True).start()
        return task_id

    def _try_local_intent(self, task_id, question, carry):
        """本地意图: 打开/关闭插件、启动外部工具 — 零 token 直执.

        置信门复用工具自身 resolver (namespace/名称精确 → 唯一模糊,
        失败返回 error 字符串且无副作用), 本地层不做第二套名称匹配;
        start 动作插件未命中且单目标时兜底 tools_operation launch;
        全部未命中返回 False — 静默交 LLM (零回归)。

        主线程执行安全: plugins_operation 内部 _run_on_ui 检测到主线程
        直接执行; tools launch 仅 spawn 进程, 均为毫秒级。
        """
        parsed = extract_open(question)
        if not parsed:
            return False
        action, targets = parsed
        name = 'plugins_operation'
        entry = registry.get(name)
        if entry is None:
            return False
        args = {'action': action, 'targets': ';'.join(targets)}
        result = entry['fn'](args)
        if isinstance(result, str) and result.startswith('error'):
            # 插件未命中 → 单目标 start 兜底外部工具 (stop 无对应)
            if action != 'start' or len(targets) != 1:
                return False
            entry = registry.get('tools_operation')
            if entry is None:
                return False
            name = 'tools_operation'
            args = {'action': 'launch', 'target': targets[0]}
            result = entry['fn'](args)
            if not (isinstance(result, str) and result.startswith('ok')):
                return False
        # 与 LLM 路径同事件流 — 面板照常出工具行, 'local' 哨兵跳过
        # tokens/耗时; result_str 形态对齐 agent 循环 (dict→JSON)
        result_str = (result if isinstance(result, str)
                      else json.dumps(result, ensure_ascii=False))
        self._q_put(('tool_call', task_id, name, args))
        self._q_put(('tool_result', task_id, name, result_str, None))
        self._q_put(('done', task_id, result_str, 'local'))
        if carry:
            # 本地操作有副作用 — 写会话让后续"关掉它"类指代有上下文
            verb = '打开' if action == 'start' else '关闭'
            self._session.append({'role': 'user', 'content': question})
            self._session.append({
                'role': 'assistant',
                'content': '已帮你%s: %s (本地匹配执行, 未调用模型)'
                           % (verb, ', '.join(targets))})
            self._session = self._trim_session(self._session)
            self._save_session()
        return True

    def _svc_stop(self, task_id):
        ev = self._stops.get(task_id)
        if ev is not None:
            ev.set()
        # 同步释放该任务阻塞中的确认等待 — 否则 worker 最长挂 120s 才退出
        c = self._confirms.get(task_id)
        if c is not None:
            c['event'].set()
        return ev is not None or c is not None

    def _svc_clear_session(self):
        """清空会话历史 — 先终止进行中的提问, 防 worker 回填畸形历史."""
        for ev in list(self._stops.values()):
            ev.set()
        for c in list(self._confirms.values()):
            c['event'].set()    # 释放阻塞中的确认等待 (同 on_stop)
        with self._lock:
            self._session = []
        self._save_session()
        return True

    def _svc_get_session(self):
        """返回会话历史拷贝 (面板回显用) — 外部修改不影响服务."""
        with self._lock:
            return list(self._session)

    def _svc_list_tools(self):
        return [{'name': t['name'], 'description': t['description'],
                 'dangerous': t['dangerous'], 'builtin': 'fn' in t,
                 'fn_ref': t.get('fn_ref')} for t in registry.list_tools()]

    def _svc_confirm_result(self, task_id, ok):
        """确认回传 (主线程弹窗后调用) — 唤醒工作线程."""
        c = self._confirms.get(task_id)
        if c is None:
            return False
        c['result'] = bool(ok)
        c['event'].set()
        return True

    def _svc_register_tool(self, name, description, schema, fn_ref,
                           dangerous=False):
        """运行时注册能力 (动态场景): fn_ref 形如 'net_tools@diag'.

        声明式注册 (_load_declared_tools) 是主渠道; 此接口供插件在
        运行时按需补充。能力函数将在 agent 工作线程执行 — 必须线程
        安全、不得操作 UI。非法输入返回 False (不抛异常)。
        """
        if (not isinstance(name, str) or not name.strip()
                or not isinstance(schema, dict)
                or not isinstance(fn_ref, str) or '@' not in fn_ref):
            return False
        registry.register(name, description, schema, fn_ref=fn_ref,
                          dangerous=dangerous)
        return True

    # ---- 工作线程 ----

    def _worker(self, task_id, question, stop, carry):
        try:
            current_config = self._config.current
            client = OpenAIClient(current_config['url'],
                                  current_config['api_key'],
                                  current_config['model'],
                                  timeout=current_config['timeout'],
                                  proxy=current_config['proxy'])
            tools = self._agent_tools()
            tool_map = {t['name']: t for t in tools}
            agent = Agent(client, tools,
                          confirm_cb=lambda n, a: self._confirm(task_id, n, a))
            user_msg = {'role': 'user', 'content': question}
            # system 约束置顶 (不进 session); 历史仅在 carry 时携带
            msgs = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
            if carry:
                msgs.extend(list(self._session[-_MAX_SESSION_MSGS:]))
            msgs.append(user_msg)
            if carry:
                with self._lock:
                    self._session.append(user_msg)
            base_len = len(msgs)   # agent 原地回填工具交换, 结束后按此截取新增段
            last_args = None
            for event in agent.run(msgs, stop_event=stop):
                kind = event[0]
                if kind == 'text':
                    self._q_put(('chunk', task_id, event[1]))
                elif kind == 'progress':
                    self._q_put(('progress', task_id, event[1], event[2]))
                elif kind == 'timing':
                    self._q_put(('timing', task_id, event[1], event[2],
                                 event[3]))
                elif kind == 'tool_call':
                    last_args = event[2]   # agent 顺序执行, 供摘要提炼目标
                    self._q_put(('tool_call', task_id, event[1], event[2]))
                elif kind == 'tool_result':
                    self._q_put(('tool_result', task_id, event[1], event[2],
                                 self._tool_summary(tool_map, event[1],
                                                    event[2], last_args)))
                elif kind == 'done' and event[1] is not None:
                    if carry and not stop.is_set():
                        with self._lock:
                            # 完整工具交换写回 session — 多轮历史须含调用过程,
                            # 否则模型学到"问→直接答"模式, 倾向于不调工具编结果
                            self._session.extend(
                                self._sessionize(msgs[base_len:]))
                            self._session.append({'role': 'assistant',
                                                  'content': event[1]})
                            self._session = self._trim_session(self._session)
                    self._q_put(('done', task_id, event[1],
                                 event[2] if len(event) > 2 else None))
                elif kind == 'done':
                    # 停止/轮数耗尽轮: 工具交换补齐配对后写回 (防下轮重做)
                    if carry:
                        with self._lock:
                            self._session.extend(self._sessionize(
                                self._close_tool_pairs(msgs[base_len:])))
                            note = ('[该请求已被用户停止]' if stop.is_set()
                                    else '[已达最大工具调用轮数]')
                            self._session.append({'role': 'assistant',
                                                  'content': note})
                            self._session = self._trim_session(self._session)
                    self._q_put(('done', task_id, '',
                                 event[2] if len(event) > 2 else None))
            self._save_session()
        except LLMError as e:
            self._q_put(('error', task_id, str(e)))
            self._mark_failed(carry, stop, str(e))
        except Exception as e:
            self._q_put(('error', task_id, 'internal: %s' % e))
            self._mark_failed(carry, stop, 'internal: %s' % e)
        finally:
            with self._lock:
                self._stops.pop(task_id, None)
            self._q_put(('status', -1))

    @staticmethod
    def _sessionize(new_msgs):
        """工具交换消息 → session 形态.

        内容即模型所见, 不做二次截断 — 截断已在 agent 层 (TOOL_RESULT_MAX)
        完成, 两层各截一次会导致"下轮看到的历史比当场决策时更短"的倒挂;
        arguments 不截断: 来自模型自身, 正常参数 <<1KB, 截断追加省略号
        反会制造非法 JSON 回流 API。
        """
        out = []
        for m in new_msgs:
            role = m.get('role')
            if role == 'assistant' and m.get('tool_calls'):
                tcs = [{'id': tc['id'], 'type': 'function',
                        'function': dict(tc['function'])}
                       for tc in m['tool_calls']]
                out.append({'role': 'assistant', 'content': m.get('content'),
                            'tool_calls': tcs})
            elif role == 'tool':
                out.append({'role': 'tool',
                            'tool_call_id': m.get('tool_call_id'),
                            'content': m.get('content') or ''})
        return out

    @staticmethod
    def _close_tool_pairs(new_msgs):
        """停止中途的尾部 assistant(tool_calls) 补占位 tool 响应, 保持配对合法."""
        ids, answered = [], set()
        for m in new_msgs:
            if m.get('role') == 'assistant':
                ids.extend(tc['id'] for tc in m.get('tool_calls') or [])
            elif m.get('role') == 'tool':
                answered.add(m.get('tool_call_id'))
        out = list(new_msgs)
        for tc_id in ids:
            if tc_id not in answered:
                out.append({'role': 'tool', 'tool_call_id': tc_id,
                            'content': '[已停止, 未执行]'})
        return out

    @staticmethod
    def _trim_session(session):
        """截断至上限并保持配对合法 — 对齐到 user 边界: 头部残留孤儿 tool
        消息 (其 assistant tool_calls 已被截掉) 会致 API 400."""
        s = session[-_MAX_SESSION_MSGS:]
        for i, m in enumerate(s):
            if m.get('role') == 'user':
                return s[i:]
        return []

    def _mark_failed(self, carry, stop, err):
        """失败轮写回 session — 让后续轮次知道该任务已尝试过 (防重做)."""
        if not carry or stop.is_set():
            return
        with self._lock:
            self._session.append({'role': 'assistant',
                                  'content': '[上次请求执行失败: %s]' % err})
            self._session = self._trim_session(self._session)

    @staticmethod
    def _tool_summary(tool_map, name, result, args):
        """计算工具结果的一行摘要 — 无 summary 函数或失败时返回 None.

        *args* 为工具调用参数, 供摘要函数提炼目标 (host/url 等)。
        """
        tool = tool_map.get(name)
        sfn = tool.get('summary') if tool else None
        if not callable(sfn):
            return None
        try:
            return sfn(result, args)
        except Exception:
            return None

    def _confirm(self, task_id, name, args):
        """工作线程调用 — 阻塞等主线程弹窗确认 (最长 2 分钟)."""
        c = {'event': threading.Event(), 'result': False}
        self._confirms[task_id] = c
        self._q_put(('confirm', task_id, name, args))
        c['event'].wait(120)
        self._confirms.pop(task_id, None)
        return c['result']

    def _agent_tools(self):
        """注册表工具 → agent 工具 (fn_ref 包装为 services.call)."""
        tools = []
        for t in registry.list_tools():
            if 'fn' in t:
                tools.append(t)
            else:
                ref = t['fn_ref']
                tools.append({**t, 'fn': self._make_caller(ref)})
        return tools

    def _make_caller(self, ref):
        """fn_ref 调用器 — 插件未启动时隐藏启动后重试一次 (同 tasks 懒启动)."""
        def caller(args):
            plugin_ns = ref.split('@', 1)[0]
            try:
                plugin_status = self.services.call('plugins@check', plugin_ns)
            except:
                plugin_status = -1
            if plugin_status < 0:
                # 插件不存在, 直接返回错误
                return 'error: capability unavailable (%s)' % ref
            alive = plugin_status > 0
            if not alive:
                # 插件存在, 但是没启动, 先尝试启动
                # 启动必须落在主线程 (Tk 非线程安全) — after 调度, 同 task_service
                self.root.after(0, lambda ns=plugin_ns: self.services.call('plugins@start', ns, hidden=True))
                # 检测插件是否启动，最大检测时间为2s
                self.services.call('plugins@check', plugin_ns, 2)
            # 尝试调用插件的服务
            try:
                return self.services.call(ref, **args)
            except KeyError:
                return 'error: capability unavailable (%s)' % ref
            finally:
                if not alive:
                    # 自行启动的插件，在执行完后自动关闭
                    # 停止必须落在主线程 (Tk 非线程安全) — after 调度, 同 task_service
                    self.root.after(0, lambda ns=plugin_ns: self.services.call('plugins@stop', ns))
        return caller

    # ---- 事件队列 (线程 → 主线程) ----

    def _q_put(self, item):
        self._queue.put(item)
        try:
            self.root.event_generate('<<AgentPoll>>', when='tail')
        except Exception:
            pass

    def _on_poll(self, _event):
        """主线程 drain: emit 事件 / 弹确认 / 更新状态.

        每条消息单独隔离 — 订阅者回调异常不打断服务事件泵.
        """
        try:
            while True:
                msg = self._queue.get_nowait()
                try:
                    self._dispatch(msg)
                except Exception:
                    pass
        except queue.Empty:
            pass

    def _dispatch(self, msg):
        kind = msg[0]
        if kind == 'chunk':
            self.app.emit('chunk', msg[1], msg[2])
        elif kind == 'local':
            self.app.emit('local', msg[1], msg[2])
        elif kind == 'progress':
            self.app.emit('progress', msg[1], msg[2], msg[3])
        elif kind == 'timing':
            self.app.emit('timing', msg[1], msg[2], msg[3], msg[4])
        elif kind == 'tool_call':
            self.app.emit('tool_call', msg[1], msg[2], msg[3])
        elif kind == 'tool_result':
            self.app.emit('tool_result', msg[1], msg[2], msg[3],
                          msg[4] if len(msg) > 4 else None)
        elif kind == 'done':
            self.app.emit('done', msg[1], msg[2],
                          msg[3] if len(msg) > 3 else None)
        elif kind == 'error':
            self.app.emit('error', msg[1], msg[2])
        elif kind == 'confirm':
            self._handle_confirm(msg)
        elif kind == 'status':
            self._set_status(self._busy + msg[1])

    def _handle_confirm(self, msg):
        """危险工具确认弹窗 (主线程, 主题化组件) — 异常默认拒绝, 永不抛穿."""
        _, task_id, name, args = msg
        detail = json.dumps(args, ensure_ascii=False, indent=2)
        # 大参数工具的 arguments 可能数万字符 — 截断防弹窗卡死
        if len(detail) > 2000:
            detail = detail[:2000] + '\n… (内容过长已截断)'
        try:
            ok = self.components.askyesno(
                '%s — %s' % ('小U' if self.app.current_lang_name == 'zh' else 'U-Bot', name),
                '执行工具 %s?\n\n%s' % (name, detail),
                parent=self._win or self.root)
        except Exception:
            ok = False
        self._svc_confirm_result(task_id, ok)

    def _set_status(self, n):
        self._busy = max(0, n)
        self.store.commit('status', 'busy' if self._busy > 0 else 'idle')

    def _load_session(self):
        s = load_json(_SESSION_PATH, [])
        return s if isinstance(s, list) else []

    # ---- 持久化 ---

    def _save_session(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(_SESSION_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._session, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
