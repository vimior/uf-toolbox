# Task Scheduler Reference

## Panel Controls

| Action | Description |
|--------|-------------|
| `Import` | Import tasks from JSON (skip duplicate IDs) |
| `Export` | Select tasks and export to JSON |
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
| `start_time` | str/int/float | Optional, timing anchor. Accepts Unix timestamp, `"HH:MM:SS"`, or `"YYYY-MM-DD HH:MM:SS"`. If unset, count from creation/activation time |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `max_runs` | int | Max executions (0=unlimited, default 0) |
| `timeout` | int | Per-call timeout in seconds (0=none, default 0) |
| `args` | tuple | Positional args passed to target |
| `kwargs` | dict | Keyword args passed to target |

**Example:**
```
tasks@create_every('ping', 30, 'demo@hello', max_runs=100)
tasks@create_every('aligned', 10, 'demo@tick', start_time='10:00:00')
```
> With `start_time`, fire times are `start_time + N × interval` (N=1,2,3…). Pause/resume preserves the grid alignment.

### once — One-shot

Runs once after N seconds, or at a specific time.

**Params:**

| Param | Type | Description |
|-------|------|-------------|
| `task_id` | str | Unique task identifier |
| `delay` | str or float | Relative seconds (e.g. `60`), time `"HH:MM"` / `"HH:MM:SS"`, Unix timestamp, or absolute datetime `"YYYY-MM-DD HH:MM:SS"` |
| `fn_ref` | str | Target service |
| `auto_start` | bool | Auto-start plugin if offline (default True) |
| `timeout` | int | Per-call timeout in seconds |
| `args` | tuple | Positional args |
| `kwargs` | dict | Keyword args |

**Example:**
```
tasks@create_once('init', 5, 'demo@setup')
tasks@create_once('daily_job', '09:00', 'demo@report')
tasks@create_once('meeting', '2026-08-05 14:30:00', 'notify@popup', title='Meeting', timeout=0)
```
> Past time → next day; absolute datetime → exact; large numbers → relative seconds.

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
| `args` | tuple | Positional args |
| `kwargs` | dict | Keyword args |

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
| `args` | tuple | Positional args |
| `kwargs` | dict | Keyword args |

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
| `args` | tuple | Positional args |
| `kwargs` | dict | Keyword args |

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
| `tasks@resume(task_id)` | Resume (pause→keeps cadence; failure→resets timer) |
| `tasks@list()` | List all tasks with status |
| `tasks@get(task_id)` | Get detailed info for one task |

---

## Import / Export

- **Export**: Select tasks → save as JSON. Only type-specific config fields are exported (no runtime state).
- **Import**: Choose JSON file → merge with existing tasks. Duplicate IDs are skipped; paused state is preserved.
- Persistence file: `~/.uf_toolbox/tasks.json`, auto-loaded on startup.

---

## Notification Service (notify)

Built-in popup notifications usable via `fn_ref` in tasks. All types refresh existing windows on repeat calls instead of creating new ones. `text=None` uses built-in i18n defaults.

- toast: Notice / 新通知
- popup: Notification / 通知
- banner: Heads up / 新消息
- canvas: Hello! / 你好！

### notify@toast — Corner notification

Slides in from a screen corner. Click starts a 3-second auto-close countdown.

| Param | Default | Description |
|-------|---------|-------------|
| `text` | `None` | Display text |
| `timeout` | `3` | Auto-close seconds, 0=never |
| `duration` | `300` | Slide animation duration ms |
| `position` | `'br'` | `tl`/`tr`/`bl`/`br` |
| `x`, `y` | `None` | Exact coordinates (overrides position) |
| `width` | `0` | Width, 0=auto |
| `height` | `0` | Height, 0=auto |
| `bg` | `#333` | Background |
| `fg` | `#fff` | Text color |
| `font_size` | `10` | Font size |

```
notify@toast('Task done', timeout=3, position='br')
notify@toast(bg='#1a8a3a', fg='#fff')
```

### notify@popup — Centered dialog

Centered dialog. Close via X button.

| Param | Default | Description |
|-------|---------|-------------|
| `text` | `None` | Display text |
| `title` | `None` | Window title, None=i18n default |
| `timeout` | `0` | Auto-close seconds, 0=never |
| `width` | `360` | Width |
| `height` | `200` | Height |
| `x`, `y` | `None` | Exact coordinates, None=center |
| `bg` | `#2b2b2b` | Background |
| `fg` | `#e0e0e0` | Text color |
| `font_size` | `10` | Font size |

```
notify@popup('Important', title='Warning', timeout=0)
notify@popup('Service restarted', width=400, height=150)
```

### notify@banner — Top banner

Full-width strip sliding down from top. Click starts a 3-second auto-close countdown.

| Param | Default | Description |
|-------|---------|-------------|
| `text` | `None` | Display text |
| `timeout` | `5` | Auto-close seconds, 0=never |
| `duration` | `400` | Slide animation duration ms |
| `width` | `0` | Width, 0=full screen |
| `height` | `0` | Height, 0=auto |
| `bg` | `#2d5a8a` | Background |
| `fg` | `#fff` | Text color |
| `font_size` | `11` | Font size |

```
notify@banner('Maintenance in 5 min', timeout=10, bg='#c0392b')
```

### notify@canvas — Decorative pattern

Canvas-drawn decorative popup. Close via X button.

| Param | Default | Description |
|-------|---------|-------------|
| `text` | `None` | Display text |
| `pattern` | `'flower'` | `flower` / `heart` / `star` / `sun` / `smiley` |
| `title` | `None` | Window title, None=auto emoji per pattern |
| `timeout` | `0` | Auto-close seconds, 0=never |
| `width` | `None` | Width, None=auto per pattern |
| `height` | `None` | Height, None=auto per pattern |
| `x`, `y` | `None` | Exact coordinates, None=center |
| `bg` | `#1a1a2e` | Background |
| `fg` | `#f0e68c` | Text color |
| `font_size` | `13` | Font size |
| `show_time` | `True` | Show timestamp |

**Pattern sizes:** flower(300×360), heart/star/smiley(280×300), sun(300×310)

```
notify@canvas('Great work!', pattern='heart')
notify@canvas('Good morning', pattern='sun', show_time=False)
notify@canvas(timeout=30)  -- uses default text
```

### With Task Scheduler

```
tasks@create_once('greet', 5, 'notify@canvas', kwargs={'text': 'Hello', 'pattern': 'flower', 'timeout': 10})
tasks@create_every('notify_ping', 30, 'notify@toast', kwargs={'text': 'Ping OK', 'timeout': 3})
tasks@create_once('reminder', '14:00', 'notify@popup', kwargs={'text': 'Meeting', 'title': 'Reminder', 'timeout': 0})
```

---

## Target Format

**Format:** `namespace@method`

- Single target: `demo@hello`
- Multiple targets (comma-separated): `demo@step1, demo@step2, notify@toast`
- With arguments: use `args` / `kwargs` in `tasks@create_xxx`

> Multi-target calls each in order; any failure fails the whole run.

---

## Behavior Notes

- **Persistence:** Task configs auto-saved to `~/.uf_toolbox/tasks.json`, restored on restart
- **Startup:** every tasks reset `last_run` on load to avoid immediate re-trigger
- **Auto-start:** If target plugin is offline, it is started in background and the call retried
- **Prewarm:** Plugins probed and started 5s before trigger (30s cooldown per namespace)
- **Timeout:** Counts actual call time only; startup time tracked as `startup_ms`
- **Pause/Resume:** Pause→resume preserves cadence; failure→retry resets timer
- **Edit:** Preserves execution stats (count, avg, history); revives failed/disabled tasks
- **History:** Last 10 execution records kept
