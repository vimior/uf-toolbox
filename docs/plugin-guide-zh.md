# 插件开发指南

UF Toolbox 支持用户自行开发两种类型的插件：**GUI 插件**（带窗口交互）和 **Service 插件**（无窗口后台服务）。插件只需放到指定目录即可自动发现，无需修改主程序。

---

## 放哪里

插件路径可在设置 → 配置中修改。默认路径为软件所在目录下的 `plugins/` 文件夹。将插件包放入该目录即可，程序启动/点击插件菜单时自动扫描发现。



---

## 目录结构

每个插件一个文件夹：

```
你的插件名/
    __init__.py       ← 必须：from .模块名 import 类名
    模块名.py          ← 插件主代码
```

`__init__.py` 示例：

```python
from .my_plugin import MyPlugin
```

---

## GUI 插件

GUI 插件继承 `GuiPlugin`，本质是一个 tkinter `Toplevel` 窗口。

### 最小示例

```python
import tkinter as tk
from plugins.plugin import GuiPlugin

class MyPlugin(GuiPlugin):
    name = "我的插件"           # 菜单显示名
    name_zh = "我的插件"        # 中文名（可选）
    name_en = "My Plugin"      # 英文名（可选）
    namespace = "my_plugin"    # 隔离命名空间

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.title(self.name)
        tk.Label(self, text="Hello!").pack(padx=20, pady=20)

    def on_show(self):
        """窗口打开或从隐藏恢复时调用"""

    def on_hide(self):
        """窗口关闭但保留实例时调用（仅 reload=False 时触发）"""

    def on_destroy(self):
        """窗口销毁时调用，做最终清理"""
```

打开菜单 → Plugins → 点击即可启动。

### 可配置的参数

在类体上定义以下属性（AST 扫描读取，不需要实例化）：

| 参数 | 类型 | 默认 | 说明 |
|------|------|:---:|------|
| `name` | str | — | 菜单显示名称（必填） |
| `name_zh` | str | — | 中文环境下的显示名 |
| `name_en` | str | — | 英文环境下的显示名 |
| `namespace` | str | — | Store/Service 命名空间，用于隔离不同插件的数据和服务。默认为插件目录名，建议显式指定 |
| `priority` | int | `0` | 菜单中的排序，越大越靠前 |
| `reload` | bool | `True` | 关闭后是否重新加载。`True`=每次打开重新初始化。`False`=隐藏复用 |
| `fixed_position` | bool | `True` | 是否跟随主窗口位置 |
| `fixed_size` | bool | `True` | 是否锁定为默认尺寸 |
| `use_app_icon` | bool | `True` | 是否使用主程序图标 |
| `auto_start` | bool | `False` | 应用启动时自动打开此插件 |
| `start_hidden` | bool | `False` | 配合 `auto_start`，启动后隐藏窗口 |

---

## Service 插件

Service 插件继承 `ServicePlugin`，没有窗口，提供跨插件的函数调用。

### 最小示例

```python
from plugins.plugin import ServicePlugin

class MyService(ServicePlugin):
    name = "我的服务"
    name_zh = "我的服务"
    name_en = "My Service"
    namespace = "my_service"
    auto_start = False          # 是否跟随软件自启

    def on_start(self):
        """服务启动时调用。在此注册 services、监听事件"""
        self.app.services.register('add', lambda a, b: a + b)
        self.app.services.register('greet', self._greet)

    def _greet(self, name):
        return f"Hello, {name}!"

    def on_stop(self):
        """服务停止时调用。框架会自动清理 services 和事件监听"""
```

### 可配置的参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|:---:|------|
| `name` | str | — | 菜单显示名称（必填） |
| `name_zh` | str | — | 中文环境下的显示名 |
| `name_en` | str | — | 英文环境下的显示名 |
| `namespace` | str | — | Service 命名空间，用于隔离不同插件的数据和服务。默认为插件目录名，建议显式指定 |
| `priority` | int | `0` | 菜单中的排序，越大越靠前 |
| `auto_start` | bool | `False` | 应用启动时自动运行此服务 |

---

## 插件间通信：三大组件

插件实例通过 `self.app` 访问三大共享组件。所有名称统一使用 `namespace@name` 格式：短名（不含 `@`）自动加 `namespace@` 前缀，全限定名（含 `@`）按原样传递。插件停止时框架自动清理该命名空间下的所有监听和服务。

### 1. EventBus — 事件总线

```python
# 监听自己 namespace 下的事件（停止时自动取消）
self.app.on('data-ready', self._on_data_ready)

def _on_data_ready(self, payload):
    print(f"Data received: {payload}")

# 发送事件（自动带 namespace@ 前缀）
self.app.emit('data-ready', {'key': 'value'})

# 监听其他插件的事件（全限定名）
self.app.on('other_plugin@data-ready', self._on_other_data)

# 向其他插件发送事件（全限定名）
self.app.emit('other_plugin@data-ready', {'key': 'value'})
```

### 2. Store — 共享状态

```python
# 写入（自动加 namespace@ 前缀，如 my_plugin@my_key）
self.app.store.commit('my_key', 42)

# 读取自己的值
val = self.app.store.get('my_key')

# 读取其他插件的值（全限定 key，用 @ 分隔 namespace）
val = self.app.store.get('other_plugin@their_key')

# 订阅自己的变化（停止时自动取消）
self.app.store.subscribe('my_key', self._on_my_key_changed)

# 订阅其他插件的变化（全限定 key）
self.app.store.subscribe('other_plugin@their_key', self._on_their_key_changed)
```

### 3. Services — 远程调用

```python
# 注册函数（自动加 namespace@ 前缀）
self.app.services.register('add', lambda a, b: a + b)

# 调用自身 namespace 下的服务（自动加前缀）
result = self.app.services.call('add', 1, 2)

# 调用其他插件的服务（全限定名）
result = self.app.services.call('other_plugin@sub', 5, 3)

# 检查服务是否存在
if self.app.services.has('other_plugin@sub'):
    ...
```

### 框架生命周期事件

可监听以下事件了解其他插件的状态变化：

| 事件 | 触发时机 |
|------|---------|
| `plugins@hook:will-start` / `plugins@hook:did-start` | Service 插件启动 |
| `plugins@hook:will-stop` / `plugins@hook:did-stop` | Service 插件停止 |
| `plugins@hook:will-show` / `plugins@hook:did-show` | GUI 插件窗口打开 |
| `plugins@hook:will-hide` / `plugins@hook:did-hide` | GUI 插件窗口隐藏 |
| `plugins@hook:will-destroy` / `plugins@hook:did-destroy` | GUI 插件窗口销毁 |

回调函数接收一个 `HookInfo` 实例，包含以下只读字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `namespace` | str | 触发事件的插件命名空间 |
| `name` | str | 触发事件的插件显示名 |
| `is_service` | bool | 是否为 ServicePlugin |
| `alive` | bool | 插件是否存活 |
| `visible` | bool | GUI 插件是否可见（Service 始终 False） |

```python
from plugins.plugin import GuiPlugin, HookInfo

class MyPlugin(GuiPlugin):
    namespace = "my_plugin"

    def init(self):
        # 监听其他插件的生命周期
        self.app.on('plugins@hook:did-start', self._on_other_started)

    def _on_other_started(self, info: HookInfo):
        if info.namespace == self.namespace:
            return  # 不关心自己
        print(f"{info.name} ({info.namespace}) started")
```

---

## 完整 GUI 插件模板

```python
import tkinter as tk
from plugins.plugin import GuiPlugin

class MyPlugin(GuiPlugin):
    name = "我的插件"
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

        # 写入共享状态
        self.app.store.commit('status', 'ready')

        # 监听其他插件的状态变化（推荐 subscribe 而非直接监听 store:changed:）
        self.app.store.subscribe('other@state', self._on_other_state)

    def _on_other_state(self, new_val, old_val):
        print(f"Other plugin state: {old_val} -> {new_val}")

    def on_show(self):
        print("窗口已显示")

    def on_destroy(self):
        print("窗口已销毁")
```

## 完整 Service 插件模板

```python
from plugins.plugin import ServicePlugin

class MyService(ServicePlugin):
    name = "我的服务"
    name_zh = "我的服务"
    name_en = "My Service"
    namespace = "my_service"
    auto_start = False

    def on_start(self):
        self.app.services.register('add', lambda a, b: a + b)
        self.app.services.register('get_status', self._get_status)
        self.app.store.commit('counter', 0)
        # 监听服务注册/注销事件（推荐用 on_registered，而非直接监听 services@registered）
        self.app.services.on_registered(self._on_new_service)

    def _get_status(self):
        return "running"

    def _on_new_service(self, name):
        print(f"New service registered: {name}")

    def on_stop(self):
        print("服务停止")
```

---

## 调试

打开菜单 → 插件审查器（Plugin Inspector），可实时查看：

- 所有活跃事件和监听者
- 所有 Store 键值对和订阅关系
- 所有已注册的 Service 函数
