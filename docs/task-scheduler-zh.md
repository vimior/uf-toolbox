# 任务调度器 使用说明

## 面板操作

| 操作 | 说明 |
|------|------|
| `导入` | 从 JSON 文件导入任务（同 ID 跳过） |
| `导出` | 勾选任务导出为 JSON |
| `+ 新建` | 创建新任务 |
| `全部暂停` / `全部恢复` | 暂停/恢复所有活跃任务（不改变调度参数） |
| `?` | 打开本说明 |
| 点击任务行 | 展开/折叠执行详情 |
| `✎` | 编辑任务 |
| `⏸` / `▶` | 暂停/恢复单个任务 |
| `×` | 删除任务 |

**列：** `ID` `类型` `上次执行` `状态`

**分组：** 活跃 → 失败 → 停用 → 完成

### 状态说明

| 状态 | 含义 |
|------|------|
| 活跃 | 正常运行，等待触发 |
| 运行中 | 当前正在执行 |
| 失败 | 执行出错，已自动暂停（点 ▶ 重试） |
| 停用 | 手动暂停或全部暂停 |
| 完成 | once 已执行 / 达到最大次数 |
| 失效 | 不可恢复的错误 |

---

## 任务类型

### every — 周期执行

每隔 N 秒执行一次。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务 ID（唯一标识） |
| `interval_s` | float | 间隔秒数 |
| `fn_ref` | str | 目标服务 `namespace@method` |
| `start_time` | str/int/float | 可选，计时锚点。支持 Unix 时间戳、`"HH:MM:SS"`、`"YYYY-MM-DD HH:MM:SS"`。未设置则从创建/激活时刻开始计时 |
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `max_runs` | int | 最大执行次数（0=不限，默认 0） |
| `timeout` | int | 单次超时秒数（0=不限，默认 0） |
| `args` | tuple | 传递给目标的位置参数 |
| `kwargs` | dict | 传递给目标的关键字参数 |

**示例：**
```
tasks@create_every('ping', 30, 'demo@hello', max_runs=100)
tasks@create_every('aligned', 10, 'demo@tick', start_time='10:00:00')
```
> 有 `start_time` 时，触发时间为 `start_time + N × interval`（N=1,2,3…），实现精确对齐。暂停恢复保持网格不变。

### once — 一次性执行

延迟指定时间后执行一次，或指定时刻执行。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务 ID |
| `delay` | str 或 float | 相对秒数（如 `60`），时刻（如 `"14:30"`），Unix 时间戳，或绝对日期时间（如 `"2026-08-05 14:30:00"`） |
| `fn_ref` | str | 目标服务 |
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `timeout` | int | 超时秒数 |
| `args` | tuple | 位置参数 |
| `kwargs` | dict | 关键字参数 |

**示例：**
```
tasks@create_once('init', 5, 'demo@setup')
tasks@create_once('daily_job', '09:00', 'demo@report')
tasks@create_once('meeting', '2026-08-05 14:30:00', 'notify@popup', title='开会啦', timeout=0)
```
> 过去时刻 → 顺延明天；绝对日期 → 精确到时；大数字 → 相对秒数。

### daily — 每日定时

每天在指定时刻执行。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务 ID |
| `time_str` | str | 时刻 `"HH:MM"` 或 `"HH:MM:SS"` |
| `fn_ref` | str | 目标服务 |
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `max_runs` | int | 最大执行次数（0=不限） |
| `timeout` | int | 超时秒数 |
| `args` | tuple | 位置参数 |
| `kwargs` | dict | 关键字参数 |

**示例：**
```
tasks@create_daily('cleanup', '03:00:00', 'demo@clean')
```
> 创建时若当前已过 03:00，则明天 03:00 首次执行。

### weekly — 每周定时

每周指定几天，在指定时刻执行。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务 ID |
| `days` | list[int] | 星期列表（0=周一 … 6=周日），如 `[0,3,5]` |
| `time_str` | str | 时刻 `"HH:MM"` 或 `"HH:MM:SS"` |
| `fn_ref` | str | 目标服务 |
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `max_runs` | int | 最大执行次数 |
| `timeout` | int | 超时秒数 |
| `args` | tuple | 位置参数 |
| `kwargs` | dict | 关键字参数 |

**示例：**
```
tasks@create_weekly('report', [0,2,4], '09:00', 'demo@report')
```
> 周一、三、五 09:00 执行。

### cron — Cron 表达式

标准 5 段 cron 调度。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务 ID |
| `cron_expr` | str | `"分 时 日 月 周"` 五段式 |
| `fn_ref` | str | 目标服务 |
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `max_runs` | int | 最大执行次数 |
| `timeout` | int | 超时秒数 |
| `args` | tuple | 位置参数 |
| `kwargs` | dict | 关键字参数 |

**别名：** `@yearly` `@monthly` `@weekly` `@daily` `@hourly`

**示例：**
```
tasks@create_cron('heartbeat', '*/5 * * * *', 'demo@ping')
tasks@create_cron('daily2', '@daily', 'demo@backup')
```

---

## 管理服务

| 服务 | 说明 |
|------|------|
| `tasks@cancel(task_id)` | 删除任务（不可恢复） |
| `tasks@pause(task_id)` | 暂停单个任务（保留调度参数） |
| `tasks@resume(task_id)` | 恢复单个任务（暂停→保持节奏；失败→重置计时） |
| `tasks@list()` | 列出全部任务状态 |
| `tasks@get(task_id)` | 获取单个任务详情 |

---

## 导入 / 导出

- **导出**：勾选任务 → 保存为 JSON。按类型导出专属字段（不导出运行时状态）。
- **导入**：选择 JSON 文件 → 合并到现有任务。同 ID 的任务跳过，暂停状态保留。
- 持久化文件：`~/.uf_toolbox/tasks.json`，启动时自动加载。

---

## 通知服务 (notify)

内置四种弹窗通知样式，可在任务中通过 `fn_ref` 调用。

所有通知 `text` 为 `None` 时使用内置 i18n 默认文案（toast: 新通知/Notice，popup: 通知/Notification，banner: 新消息/Heads up，canvas: 你好！/Hello!）。同类型重复调用刷新现有窗口而非新建。

### notify@toast — 角落通知

从屏幕角落滑入的轻量通知，点击后 3 秒自动关闭。

| 参数 | 默认 | 说明 |
|------|------|------|
| `text` | `None` | 显示文本 |
| `timeout` | `3` | 自动关闭秒数，0=不关 |
| `duration` | `300` | 滑入动画时长 ms |
| `position` | `'br'` | `tl`/`tr`/`bl`/`br` |
| `x`, `y` | `None` | 精确坐标，设了则忽略 position |
| `width` | `0` | 宽度，0=自适应 |
| `height` | `0` | 高度，0=自适应 |
| `bg` | `#333` | 背景色 |
| `fg` | `#fff` | 文字色 |
| `font_size` | `10` | 字号 |

```
notify@toast('任务完成', timeout=3, position='br')
notify@toast(bg='#1a8a3a', fg='#fff')
```

### notify@popup — 居中弹窗

居中对话框，点击 X 关闭。

| 参数 | 默认 | 说明 |
|------|------|------|
| `text` | `None` | 显示文本 |
| `title` | `None` | 窗口标题，None 时用 i18n 默认 |
| `timeout` | `0` | 自动关闭秒数，0=不关 |
| `width` | `360` | 宽度 |
| `height` | `200` | 高度 |
| `x`, `y` | `None` | 精确坐标，None=居中 |
| `bg` | `#2b2b2b` | 背景色 |
| `fg` | `#e0e0e0` | 文字色 |
| `font_size` | `10` | 字号 |

```
notify@popup('重要提醒', title='警告', timeout=0)
notify@popup('服务重启成功', width=400, height=150)
```

### notify@banner — 顶部横幅

从屏幕顶部滑下的全宽通知条，点击后 3 秒关闭。

| 参数 | 默认 | 说明 |
|------|------|------|
| `text` | `None` | 显示文本 |
| `timeout` | `5` | 自动关闭秒数，0=不关 |
| `duration` | `400` | 滑入动画时长 ms |
| `width` | `0` | 宽度，0=全屏宽 |
| `height` | `0` | 高度，0=自适应 |
| `bg` | `#2d5a8a` | 背景色 |
| `fg` | `#fff` | 文字色 |
| `font_size` | `11` | 字号 |

```
notify@banner('系统将在 5 分钟后维护', timeout=10, bg='#c0392b')
```

### notify@canvas — 装饰图案

Canvas 图案弹窗，点击 X 关闭。

| 参数 | 默认 | 说明 |
|------|------|------|
| `text` | `None` | 显示文本 |
| `pattern` | `'flower'` | `flower` / `heart` / `star` / `sun` / `smiley` |
| `title` | `None` | 窗口标题，None 时根据 pattern 自动匹配 emoji |
| `timeout` | `0` | 自动关闭秒数，0=不关 |
| `width` | `None` | 宽度，None=根据 pattern 自动选择 |
| `height` | `None` | 高度，None=根据 pattern 自动选择 |
| `x`, `y` | `None` | 精确坐标，None=居中 |
| `bg` | `#1a1a2e` | 背景色 |
| `fg` | `#f0e68c` | 文字色 |
| `font_size` | `13` | 字号 |
| `show_time` | `True` | 是否显示时间戳 |

**图案尺寸：** flower(300×360)、heart/star/smiley(280×300)、sun(300×310)

```
notify@canvas('辛苦了！', pattern='heart')
notify@canvas('早上好', pattern='sun', show_time=False)
notify@canvas(timeout=30)  -- 使用默认文案
```

### 配合任务调度器

```
tasks@create_once('greet', 5, 'notify@canvas', kwargs={'text': '你好', 'pattern': 'flower', 'timeout': 10})
tasks@create_every('notify_ping', 30, 'notify@toast', kwargs={'text': 'ping 完成', 'timeout': 3})
tasks@create_once('reminder', '14:00', 'notify@popup', kwargs={'text': '开会啦', 'title': '提醒', 'timeout': 0})
```

---

## 目标格式

**格式：** `namespace@method`

- 单个目标：`demo@hello`
- 多个目标（逗号分隔）：`demo@step1, demo@step2, notify@toast`
- 带参数的任务：使用 `tasks@create_xxx` 的 `args` / `kwargs` 传参

> 多目标逐个调用，任一失败则整次计为失败。

---

## 行为说明

- **持久化：** 任务配置自动保存到 `~/.uf_toolbox/tasks.json`，重启恢复
- **重启加载：** every 任务重新计时（`last_run = now`），避免启动立刻触发
- **离线自动启动：** 若目标插件未在线，自动后台启动后重试（不弹出窗口）
- **预启动：** 提前 5 秒探测并拉起离线插件，30 秒内同 namespace 不重复发
- **超时计时：** `timeout` 只计实际调用耗时，插件启动耗时单独统计（`startup_ms`）
- **暂停恢复：** 暂停→恢复保持原有节奏；失败→重试重置计时
- **编辑任务：** 保留执行统计（次数/耗时/历史）、自动复活失败/停用任务
- **执行历史：** 保留最近 10 次记录
