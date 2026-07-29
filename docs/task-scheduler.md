# Task Scheduler Reference

## Panel Controls

| Action | Description |
|--------|-------------|
| `+ Add` | Create a new task |
| `Pause All` / `Resume All` | Suspend/resume all active tasks (keeps schedule params) |
| `?` | Open this help |
| Click row | Expand/collapse execution details |
| `✎` | Edit task |
| `⏸` / `▶` | Pause/resume single task |
| `×` | Delete task |

**Columns:** `ID` `Type` `Last Run` `Status`

**Groups:** active → failed → off → done

### Status

| Status | Meaning |
|--------|---------|
| active | Normal, waiting for trigger |
| running | Currently executing |
| failed | Execution error, auto-paused (click ▶ to retry) |
| off | Manually or globally paused |
| done | once completed / max_runs reached |
| dead | Unrecoverable error |

---

## Task Types

### every — Periodic

Runs every N seconds.

**Params:**

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | str | Unique task identifier |
| `interval_s` | float | Interval in seconds |
| `fn_ref` | str | Target service `namespace@method` |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `max_runs` | int | Max executions (0=unlimited, default 0) |
| `timeout` | int | Per-call timeout in seconds (0=none, default 0) |

**Example:**
```
tasks@create_every('ping', 30, 'demo@hello', max_runs=100)
```

### once — One-shot

Runs once after N seconds, or at a specific time.

**Params:**

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | str | Unique task identifier |
| `delay` | str or float | Seconds (e.g. `60`) or time `"HH:MM"` / `"HH:MM:SS"` |
| `fn_ref` | str | Target service |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `timeout` | int | Per-call timeout in seconds |

**Example:**
```
tasks@create_once('init', 5, 'demo@setup')
tasks@create_once('daily_job', '09:00', 'demo@report')
```
> If 09:00 already passed today, runs tomorrow at 09:00.

### daily — Daily

Runs every day at the specified time.

**Params:**

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | str | Unique task identifier |
| `time_str` | str | Time `"HH:MM"` or `"HH:MM:SS"` |
| `fn_ref` | str | Target service |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `max_runs` | int | Max executions (0=unlimited) |
| `timeout` | int | Per-call timeout in seconds |

**Example:**
```
tasks@create_daily('cleanup', '03:00:00', 'demo@clean')
```

### weekly — Weekly

Runs on specified weekdays at the specified time.

**Params:**

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | str | Unique task identifier |
| `days` | list[int] | Days: 0=Mon … 6=Sun, e.g. `[0,3,5]` |
| `time_str` | str | Time `"HH:MM"` or `"HH:MM:SS"` |
| `fn_ref` | str | Target service |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `max_runs` | int | Max executions |
| `timeout` | int | Per-call timeout in seconds |

**Example:**
```
tasks@create_weekly('report', [0,2,4], '09:00', 'demo@report')
```

### cron — Cron Expression

Standard 5-field cron scheduling.

**Params:**

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | str | Unique task identifier |
| `cron_expr` | str | `"min hour dom month dow"` (5 fields) |
| `fn_ref` | str | Target service |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `max_runs` | int | Max executions |
| `timeout` | int | Per-call timeout in seconds |

**Aliases:** `@yearly` `@monthly` `@weekly` `@daily` `@hourly`

**Example:**
```
tasks@create_cron('heartbeat', '*/5 * * * *', 'demo@ping')
tasks@create_cron('daily2', '@daily', 'demo@backup')
```

---

## Management Services

| Service | Description |
|---------|-------------|
| `tasks@cancel(task_id)` | Delete a task (irreversible) |
| `tasks@pause(task_id)` | Pause a single task |
| `tasks@resume(task_id)` | Resume a single task (no catch-up) |
| `tasks@list()` | List all tasks with status |
| `tasks@get(task_id)` | Get detailed info for one task |

---

## Target Format

**Format:** `namespace@method`

- Single: `demo@hello`
- Multiple (comma-separated): `demo@step1, demo@step2`

> Multi-target calls each in order; any failure fails the whole run.

---

## Behavior Notes

- **Auto-start:** If target plugin is offline, it is started in background (no window popup) and the call retried
- **Prewarm:** Plugins are probed and started 5s before trigger time (30s cooldown per namespace)
- **Timeout:** Only counts actual service call time; startup time tracked separately as `startup_ms`
- **Pause/Resume:** No catch-up for missed triggers; resumes waiting for next natural trigger
- **Edit:** Preserves execution stats (count, avg, history); rename creates a fresh task
- **History:** Last 10 execution records kept
