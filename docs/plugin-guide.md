# Plugin Development Guide

UF Toolbox supports two plugin types: **GUI plugins** (window-based) and **Service plugins** (headless background services). Plugins are auto-discovered — just drop them into the plugins directory.

---

## Where to Put Plugins

The plugin path is configurable under Settings → Config. The default is `plugins/` under the application directory. Drop plugin packages there — they are auto-discovered when the app starts or when the Plugins menu is opened.

---

## Directory Structure

One folder per plugin:

```
your_plugin/
    __init__.py       ← required: from .module_name import ClassName
    module_name.py    ← main plugin code
```

`__init__.py` example:

```python
from .my_plugin import MyPlugin
```

---

## GUI Plugin

GUI plugins inherit `GuiPlugin`, which is a `tkinter.Toplevel` subclass. The plugin instance **is** the window.

### Minimal Example

```python
import tkinter as tk
from plugins.plugin import GuiPlugin

class MyPlugin(GuiPlugin):
    name = "My Plugin"
    name_zh = "我的插件"
    name_en = "My Plugin"
    namespace = "my_plugin"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.title(self.name)
        tk.Label(self, text="Hello!").pack(padx=20, pady=20)

    def on_show(self):
        """Called when the window opens or restores from hide."""

    def on_hide(self):
        """Called when the window is hidden (reload=False only)."""

    def on_destroy(self):
        """Called before the window is destroyed — final cleanup."""
```

Open menu → Plugins → click to launch.

### Configurable Attributes

Define these on the class body (read via AST scan, no instantiation needed):

| Attribute | Type | Default | Description |
|-----------|------|:---:|------|
| `name` | str | — | Display name in menu (required) |
| `name_zh` | str | — | Chinese display name |
| `name_en` | str | — | English display name |
| `namespace` | str | — | Store/Service namespace for per-plugin isolation. Defaults to the plugin directory name; explicit is recommended |
| `priority` | int | `0` | Menu sort order, higher = first |
| `reload` | bool | `True` | `True` = destroy & recreate each open. `False` = hide & reuse |
| `fixed_position` | bool | `True` | Let app control window position |
| `fixed_size` | bool | `True` | Let app control window size |
| `use_app_icon` | bool | `True` | Use app icon for the window |
| `auto_start` | bool | `False` | Auto-open on app launch |
| `start_hidden` | bool | `False` | Start hidden (requires `auto_start`) |

---

## Service Plugin

Service plugins inherit `ServicePlugin`. No window — they register functions callable by other plugins.

### Minimal Example

```python
from plugins.plugin import ServicePlugin

class MyService(ServicePlugin):
    name = "My Service"
    name_zh = "我的服务"
    name_en = "My Service"
    namespace = "my_service"
    auto_start = False

    def on_start(self):
        """Service starts. Register services and listen to events here."""
        self.app.services.register('add', lambda a, b: a + b)
        self.app.services.register('greet', self._greet)

    def _greet(self, name):
        return f"Hello, {name}!"

    def on_stop(self):
        """Service stops. Framework auto-cleans registered services and listeners."""
```

### Configurable Attributes

| Attribute | Type | Default | Description |
|-----------|------|:---:|------|
| `name` | str | — | Display name in menu (required) |
| `name_zh` | str | — | Chinese display name |
| `name_en` | str | — | English display name |
| `namespace` | str | — | Service namespace for per-plugin isolation. Defaults to the plugin directory name; explicit is recommended |
| `priority` | int | `0` | Menu sort order, higher = first |
| `auto_start` | bool | `False` | Auto-start on app launch |

---

## Inter-Plugin Communication

Plugins access three shared components via `self.app`. All names use the `namespace@name` format: short names (no `@`) are auto-prefixed with `namespace@`, fully-qualified names (with `@`) are passed through as-is. All registrations are auto-cleaned when the plugin stops.

### 1. EventBus — Publish / Subscribe

```python
# Listen to events in your own namespace (auto-unregistered on stop)
self.app.on('data-ready', self._on_data_ready)

def _on_data_ready(self, payload):
    print(f"Data received: {payload}")

# Emit an event (auto-prefixed with namespace@)
self.app.emit('data-ready', {'key': 'value'})

# Listen to another plugin's event (fully qualified name)
self.app.on('other_plugin@data-ready', self._on_other_data)

# Emit to another plugin (fully qualified name)
self.app.emit('other_plugin@data-ready', {'key': 'value'})
```

### 2. Store — Shared State

```python
# Write (auto-prefixed, e.g. my_plugin@my_key)
self.app.store.commit('my_key', 42)

# Read your own value
val = self.app.store.get('my_key')

# Read another plugin's value (fully qualified key with @)
val = self.app.store.get('other_plugin@their_key')

# Subscribe to your own changes (auto-cancelled on stop)
self.app.store.subscribe('my_key', self._on_my_key_changed)

# Subscribe to another plugin's changes (fully qualified key)
self.app.store.subscribe('other_plugin@their_key', self._on_their_key_changed)
```

### 3. Services — Remote Calls

```python
# Register a function (auto-prefixed with namespace@)
self.app.services.register('add', lambda a, b: a + b)

# Call a service in your own namespace (auto-prefixed)
result = self.app.services.call('add', 1, 2)

# Call another plugin's service (fully qualified name)
result = self.app.services.call('other_plugin@sub', 5, 3)

# Check if another plugin's service exists (fully qualified name)
if self.app.services.has('other_plugin@sub'):
    ...
```

### Lifecycle Events

Listen to these events to track other plugins:

| Event | When |
|-------|------|
| `plugins@hook:will-start` / `plugins@hook:did-start` | Service plugin starting |
| `plugins@hook:will-stop` / `plugins@hook:did-stop` | Service plugin stopping |
| `plugins@hook:will-show` / `plugins@hook:did-show` | GUI plugin window opening |
| `plugins@hook:will-hide` / `plugins@hook:did-hide` | GUI plugin window hiding |
| `plugins@hook:will-destroy` / `plugins@hook:did-destroy` | GUI plugin window destroying |

Callbacks receive a `HookInfo` instance with these read-only fields:

| Field | Type | Description |
|-------|------|-------------|
| `namespace` | str | Namespace of the plugin that fired the event |
| `name` | str | Display name of the plugin |
| `is_service` | bool | Whether it's a ServicePlugin |
| `alive` | bool | Whether the plugin is alive |
| `visible` | bool | Whether a GUI plugin is visible (always False for services) |

```python
from plugins.plugin import GuiPlugin, HookInfo

class MyPlugin(GuiPlugin):
    namespace = "my_plugin"

    def init(self):
        # Listen for other plugins' lifecycle events
        self.app.on('plugins@hook:did-start', self._on_other_started)

    def _on_other_started(self, info: HookInfo):
        if info.namespace == self.namespace:
            return  # ignore self
        print(f"{info.name} ({info.namespace}) started")
```

---

## Window Control

The menu applies these after `__init__()`:

1. If `fixed_position=True` → set position (right of main window)
2. If `fixed_size=True` → set size (420 × main window height)
3. If `use_app_icon=True` → set window icon
4. `win.lift()` + `win.focus_force()`

Four combinations:

| fixed_position | fixed_size | Behavior |
|:---:|:---:|---|
| T | T | Fully follow main window (default) |
| T | F | Position only, plugin controls size |
| F | T | Size only, plugin controls position |
| F | F | Full freedom, plugin controls everything |

---

## Plugin Lifecycle

```
Launch → first [Plugins] click
  → scan plugins/ → import → find class → create Handle
  → click menu item → Handle.start() → cls(parent, app)
     → first time: __init__ builds UI → on_show()
     → menu sets position / size / icon
  → close (X):
     reload=True  → on_destroy() → destroy(), rebuild next time
     reload=False → on_hide() → withdraw(), instance kept
  → [Plugins] menu again → re-scan:
     + new folder → import & add
     + deleted folder → remove from menu
     + code changed → hot-reload re-import
```

---

## I18n — name_zh / name_en

**Method 1: Class attributes (recommended)**

```python
class MyPlugin(GuiPlugin):
    name_zh = "我的插件"
    name_en = "My Plugin"
    name = name_en  # fallback
```

The loader auto-selects by `current_lang_name`.

**Method 2: Dynamic in __init__**

```python
def __init__(self, parent, app):
    zh = getattr(self.app, 'current_lang_name', 'en') == 'zh'
    self.title("我的插件" if zh else "My Plugin")
```

---

## Bundling Dependencies

The plugin directory is auto-added to `sys.path`. Vendor packages directly:

```
plugins/my_plugin/
  ├── __init__.py
  ├── my_plugin.py
  └── requests/      ← pip install requests --target=.
```

Then `import requests` inside your plugin — it just works.

---

## Full GUI Plugin Template

```python
import tkinter as tk
from plugins.plugin import GuiPlugin

class MyPlugin(GuiPlugin):
    name = "My Plugin"
    name_zh = "我的插件"
    name_en = "My Plugin"
    namespace = "my_plugin"
    priority = 50
    reload = True
    fixed_size = False

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.title(self.name)
        self.geometry("400x300")

        tk.Label(self, text="Hello!").pack()

        # Write shared state
        self.app.store.commit('status', 'ready')

        # Listen for another plugin's state changes (prefer subscribe over direct store:changed:)
        self.app.store.subscribe('other@state', self._on_other_state)

    def _on_other_state(self, new_val, old_val):
        print(f"Other plugin state: {old_val} -> {new_val}")

    def on_show(self):
        print("Window shown")

    def on_destroy(self):
        print("Window destroyed")
```

## Full Service Plugin Template

```python
from plugins.plugin import ServicePlugin

class MyService(ServicePlugin):
    name = "My Service"
    name_zh = "我的服务"
    name_en = "My Service"
    namespace = "my_service"
    auto_start = False

    def on_start(self):
        self.app.services.register('add', lambda a, b: a + b)
        self.app.services.register('get_status', self._get_status)
        self.app.store.commit('counter', 0)
        # Prefer on_registered() over direct eventbus listening
        self.app.services.on_registered(self._on_new_service)

    def _get_status(self):
        return "running"

    def _on_new_service(self, name):
        print(f"New service registered: {name}")

    def on_stop(self):
        print("Service stopped")
```

---

## Debugging

Open menu → Plugin Inspector, to view in real-time:

- All active events and their listeners
- All Store key-value pairs and subscriptions
- All registered Service functions
