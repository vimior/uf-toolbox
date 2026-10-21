# -*- coding: utf-8 -*-
"""AgentService — 后台 agent 服务 (ServicePlugin, 无 UI).

服务接口 (agent@): chat / stop / clear_session / list_tools / confirm / register_tool
事件 (agent@stream): stream
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

from .config import Config, CONFIG_DIR
from .core.agent import Agent
from .core.basic_qa import match_basic_qa
from .core.llm import LLMError, OpenAIClient
from .core.local_intent import extract_open
from .core.registry import registry
from .core.session_store import SessionStore

_DB_PATH = os.path.join(CONFIG_DIR, 'agent_sessions.db')
_MAX_SESSION_MSGS = 24   # 上下文窗口 (发给 LLM 的历史条数); 库存全量不限

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
        # ---- 多会话存储 ----
        # self._session 保持 list 形态 (当前会话的内存缓存), worker 内
        # 的 _sessionize/_trim_session 等逻辑不变; 落库为增量写穿透
        # (_saved_len 记录已落盘条数). 历史窗口 _MAX_SESSION_MSGS 只
        # 限制发给 LLM 的上下文, 库中消息全量保留.
        self._store = SessionStore(_DB_PATH)
        recent = self._store.list()
        if recent:
            self._session_id = recent[0]['id']
            self._session = self._store.messages(self._session_id)
        else:
            self._session_id = self._store.create()
            self._session = []
        self._saved_len = len(self._session)
        self._win = self.root

    # ---- 生命周期 ----

    def on_start(self):
        self.services.register('chat', self._svc_chat)
        self.services.register('stop', self._svc_stop)
        self.services.register('clear_session', self._svc_clear_session)
        self.services.register('get_session', self._svc_get_session)
        self.services.register('list_sessions', self._svc_list_sessions)
        self.services.register('create_session', self._svc_create_session)
        self.services.register('switch_session', self._svc_switch_session)
        self.services.register('delete_session', self._svc_delete_session)
        self.services.register('rename_session', self._svc_rename_session)
        self.services.register('list_tools', self._svc_list_tools)
        self.services.register('confirm', self._svc_confirm_result)
        self.services.register('register_tool', self._svc_register_tool)
        self.root.bind('<<AgentPoll>>', self._on_poll)
        self.store.commit('status', 'idle')
        # 内置 6 工具 (core/tools/) 暂不注册 — 垂直场景价值低, 通用能力
        # 由插件承接; 恢复: 重新 import register_builtin 并在此调用 (幂等)

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
        try:
            self._save_session()
            self._store.close()
        except Exception:
            pass

    # ---- 服务接口 (面板/其他插件/定时任务调用) ----

    def _svc_chat(self, question, carry=True, win=None, local_first=True):
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
        start 动作插件未命中时兜底 tools_operation launch;
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
        succeed_plugins = []
        failed_plugins = []
        if isinstance(result, dict):
            for target, res in result.items():
                if isinstance(res, str) and res.startswith('failed'):
                    failed_plugins.append(target)
                else:
                    succeed_plugins.append(target)
        # elif isinstance(result, str) and result.startswith('error'):
        else:
            failed_plugins = targets
        # 与 LLM 路径同事件流 — 面板照常出工具行, 'local' 哨兵跳过
        # tokens/耗时; result_str 形态对齐 agent 循环 (dict→JSON)
        result_str = (result if isinstance(result, str)
                      else json.dumps(result, ensure_ascii=False))
        self._q_put(('tool_call', task_id, name, args))
        self._q_put(('tool_result', task_id, name, result_str, None))

        verb = '打开' if action == 'start' else '关闭'
        contents = []
        if succeed_plugins:
            contents.append('已帮你{}插件: {}'.format(verb, '/'.join(succeed_plugins)))

        succeed_tools = []
        failed_targets = []

        if action == 'start' and len(failed_plugins):
            name = 'tools_operation'
            entry = registry.get(name)
            if entry is None:
                return False
            args = {'action': 'launch', 'targets': ';'.join(failed_plugins)}
            result = entry['fn'](args)
            if isinstance(result, dict):
                for target, res in result.items():
                    if isinstance(res, str) and (res.startswith('failed') or res.startswith('error')):
                        failed_targets.append(target)
                    else:
                        succeed_tools.append(target)
            # elif isinstance(result, str) and result.startswith('error'):
            else:
                failed_targets = failed_plugins

            # 与 LLM 路径同事件流 — 面板照常出工具行, 'local' 哨兵跳过
            # tokens/耗时; result_str 形态对齐 agent 循环 (dict→JSON)
            result_str = (result if isinstance(result, str)
                            else json.dumps(result, ensure_ascii=False))
            self._q_put(('tool_call', task_id, name, args))
            self._q_put(('tool_result', task_id, name, result_str, None))
        else:
            failed_targets = failed_targets
        
        if succeed_tools:
            contents.append('已帮你{}工具: {}'.format(verb, '/'.join(succeed_tools)))
        if failed_targets:
            contents.append('无法{}: {}'.format(verb, '/'.join(failed_targets)))
        if carry:
            # 本地操作有副作用 — 写会话让后续"关掉它"类指代有上下文
            self._commit(self._session_id, [
                {'role': 'user', 'content': question},
                {'role': 'assistant',
                 'content': '\n'.join(contents)},
            ])
            self._auto_title(self._session_id, question)
        self._q_put(('chunk', task_id, '\n'.join(contents)))
        if succeed_plugins or succeed_tools:
            self._q_put(('done', task_id, '', 'local'))
            return True
        return False

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
        """清空当前会话消息 — 先终止进行中的提问, 防 worker 回填畸形历史."""
        for ev in list(self._stops.values()):
            ev.set()
        for c in list(self._confirms.values()):
            c['event'].set()    # 释放阻塞中的确认等待 (同 on_stop)
        with self._lock:
            self._store.clear(self._session_id)
            self._session = []
            self._saved_len = 0
        return True

    def _svc_get_session(self):
        """返回当前会话历史拷贝 (面板回显用) — 外部修改不影响服务."""
        with self._lock:
            return list(self._session)

    # ---- 多会话管理 ----

    def _svc_list_sessions(self):
        """全部会话 (按最后消息时间倒序): [{id,title,usage,msg_count,...}]"""
        return self._store.list()

    def _svc_create_session(self):
        """新建空会话并切换, 返回新会话 id."""
        with self._lock:
            self._save_session()
            self._session_id = self._store.create()
            self._session = []
            self._saved_len = 0
        return self._session_id

    def _svc_switch_session(self, sid):
        """切换到已有会话 (不存在返回 False)."""
        with self._lock:
            if not self._store.exists(sid):
                return False
            if sid != self._session_id:
                self._save_session()
                self._session_id = sid
                self._session = self._store.messages(sid)
                self._saved_len = len(self._session)
        return True

    def _svc_delete_session(self, sid):
        """删除会话; 若删的是当前会话则切到最近的其他会话 (没有则新建).

        :return: 删除后的当前会话 id
        """
        with self._lock:
            self._store.delete(sid)
            if sid != self._session_id:
                return self._session_id
            rest = self._store.list()
            if rest:
                self._session_id = rest[0]['id']
                self._session = self._store.messages(self._session_id)
            else:
                self._session_id = self._store.create()
                self._session = []
            self._saved_len = len(self._session)
            return self._session_id

    def _svc_rename_session(self, sid, title):
        if not self._store.exists(sid):
            return False
        self._store.rename(sid, title)
        return True

    def _svc_list_tools(self, detail=False):
        tools = []
        for t in registry.list_tools():
            tool = {
                'name': t['name'], 'description': t['description'],
                'dangerous': t['dangerous'], 'builtin': 'fn' in t,
            }
            if 'fn' not in t and 'fn_ref' in t:
                tool['fn_ref'] = t['fn_ref']
            if detail and 'schema' in t:
                tool['schema'] = t['schema']
            tools.append(tool)
        return tools

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

        声明式注册是主渠道(插件管理扫描时自动注册); 此接口供插件在
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
        # 捕获会话 id: 用户中途切换会话, 本轮写回仍落在发起时的会话,
        # 不串到新会话 (历史窗口 likewise 以捕获的会话为准)
        sid = self._session_id
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
                with self._lock:
                    if sid == self._session_id:
                        hist = list(self._session[-_MAX_SESSION_MSGS:])
                    else:
                        hist = self._store.messages(sid)[-_MAX_SESSION_MSGS:]
                msgs.extend(hist)
            msgs.append(user_msg)
            if carry:
                self._commit(sid, [user_msg], trim=False)
                self._auto_title(sid, question)
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
                elif kind == 'done':
                    usage = event[2] if len(event) > 2 else None
                    if isinstance(usage, dict):
                        # 会话级 token 累计 — 面板状态栏按会话展示
                        try:
                            self._store.add_usage(sid, usage)
                        except Exception:
                            pass
                    if event[1] is not None:
                        if carry and not stop.is_set():
                            # 完整工具交换写回 session — 多轮历史须含调用过程,
                            # 否则模型学到"问→直接答"模式, 倾向于不调工具编结果
                            self._commit(
                                sid,
                                self._sessionize(msgs[base_len:])
                                + [{'role': 'assistant',
                                    'content': event[1]}])
                        self._q_put(('done', task_id, event[1], usage))
                    else:
                        # 停止/轮数耗尽轮: 工具交换补齐配对后写回 (防下轮重做)
                        if carry:
                            note = ('[该请求已被用户停止]' if stop.is_set()
                                    else '[已达最大工具调用轮数]')
                            self._commit(
                                sid,
                                self._sessionize(
                                    self._close_tool_pairs(
                                        msgs[base_len:]))
                                + [{'role': 'assistant', 'content': note}])
                        self._q_put(('done', task_id, '', usage))
        except LLMError as e:
            self._q_put(('error', task_id, str(e)))
            self._mark_failed(sid, carry, stop, str(e))
        except Exception as e:
            self._q_put(('error', task_id, 'internal: %s' % e))
            self._mark_failed(sid, carry, stop, 'internal: %s' % e)
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

    def _mark_failed(self, sid, carry, stop, err):
        """失败轮写回 session — 让后续轮次知道该任务已尝试过 (防重做)."""
        if not carry or stop.is_set():
            return
        self._commit(sid, [{'role': 'assistant',
                            'content': '[上次请求执行失败: %s]' % err}])

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
        if kind in ['chunk', 'local', 'progress', 'timing', 'tool_call', 'tool_result', 'done', 'error']:
            self.app.emit('stream', msg[1], kind, msg[2:])
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

    # ---- 会话持久化 (sqlite 增量写穿透) ---

    def _save_session(self):
        """当前会话增量落盘: 只插内存缓存中未落盘的尾巴.

        调用方须已持有 self._lock (或处于单线程调用栈). 非当前会话的
        写回走 _commit 内对 store.append 的直调, 不经此方法.
        """
        try:
            new = self._session[self._saved_len:]
            if new:
                self._store.append(self._session_id, new)
                self._saved_len = len(self._session)
        except Exception:
            pass

    def _commit(self, sid, msgs, trim=True):
        """追加消息到指定会话.

        当前会话: 同步内存缓存并按窗口对齐 trim, 增量落盘;
        非当前会话 (用户中途切换过): 直写库, 内存缓存不动.
        调用方无须持锁 — 本方法自锁.
        """
        if not msgs:
            return
        with self._lock:
            if sid == self._session_id:
                self._session.extend(msgs)
                if trim:
                    self._session = self._trim_session(self._session)
                self._save_session()
            else:
                try:
                    self._store.append(sid, msgs)
                except Exception:
                    pass

    def _auto_title(self, sid, question):
        """首条用户消息自动生成会话标题 (10 字 — 侧栏 180px 宽度约束)."""
        try:
            title = ' '.join(str(question).split())[:10]
            if title:
                self._store.set_title_if_untitled(sid, title)
        except Exception:
            pass
