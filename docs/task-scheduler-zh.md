# 任务调度器 使用说明

## 面板操作

| 操作 | 说明 |
|------|------|
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
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `max_runs` | int | 最大执行次数（0=不限，默认 0） |
| `timeout` | int | 单次超时秒数（0=不限，默认 0） |

**示例：**
```
tasks@create_every('ping', 30, 'demo@hello', max_runs=100)
```

### once — 一次性执行

延迟指定时间后执行一次，或指定时刻执行。

**参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | str | 任务 ID |
| `delay` | str 或 float | 延迟秒数（如 `60`），或时刻（如 `"14:30"`） |
| `fn_ref` | str | 目标服务 |
| `auto_start` | bool | 目标离线时自动启动（默认 True） |
| `timeout` | int | 超时秒数 |

**示例：**
```
tasks@create_once('init', 5, 'demo@setup')
tasks@create_once('daily_job', '09:00', 'demo@report')
```
> 若当前已过 09:00，则明天 09:00 执行。

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
| `tasks@resume(task_id)` | 恢复单个任务（不补跑，等下次触发） |
| `tasks@list()` | 列出全部任务状态 |
| `tasks@get(task_id)` | 获取单个任务详情 |

---

## 目标格式

**格式：** `namespace@method`

- 单个目标：`demo@hello`
- 多个目标（逗号分隔）：`demo@step1, demo@step2`

> 多目标逐个调用，任一失败则整次计为失败。

---

## 行为说明

- **离线自动启动：** 若目标插件未在线，自动后台启动后重试（不弹出窗口）
- **预启动：** 提前 5 秒探测并拉起离线插件，30 秒内同 namespace 不重复发
- **超时计时：** `timeout` 只计实际调用耗时，插件启动耗时单独统计（`startup_ms`）
- **暂停恢复：** 不补跑已错过的触发点，恢复后等下一个自然触发时间
- **编辑任务：** 保留执行统计（次数/耗时/历史），改名则视为新建
- **执行历史：** 保留最近 10 次记录
