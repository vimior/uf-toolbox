# 自定义工具配置指南

UF Toolbox 通过 JSON 配置文件管理工具栏中的自定义工具。你可以添加自己的程序快捷启动，或覆盖已有的系统工具。

---

## 放哪里

将 `tools.json` 放到 exe 同目录下的 `tools/` 目录中即可。如果想使用自定义目录，在软件设置 → 配置中指定工具目录路径。

## 工具 ID 的构成

工具的实际 ID 由分组路径拼接而成：

| 工具所属层级 | 实际 ID（完整 ID） | 所属菜单栏 |
|------------|-------------------|-----------|
| 顶层 `tools` 数组中 | `工具自己的 id`（如 `"vscode"`） | 工具栏 |
| 顶层 `tools` 数组中，id 以 `system/` 开头 | `system/工具id` | 系统栏 |
| 顶层 `groups` 中、分组 id 不以 `system/` 开头 | `分组id/工具id` | 工具栏 |
| 顶层 `groups` 中、分组 id 以 `system/` 开头 | `system/分组id/工具id` | 系统栏 |

同完整 ID 的工具，后发现的会覆盖前面的（用于替换内置工具）。

---

## 文件格式

```json
{
  "tools": [
    { "id": "my-tool", "name": "我的工具", "path": "notepad.exe" }
  ],
  "groups": [
    { "id": "my-group", "name": "我的分组", "tools": [ ... ] }
  ]
}
```

`"tools"` 和 `"groups"` 都是可选的。分组内还可以嵌套 `"groups"`，无限层级。

---

## 工具参数

每一工具是一个 JSON 对象：

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `id` | string | 是 | 唯一标识。在分组内使用时，完整 ID = `分组路径/工具ID`（如 `system/common/notepad`）。后发现的同完整 ID 会覆盖之前的 |
| `name` | string | 是 | 显示名称 |
| `name_zh` | string | 否 | 中文环境名称（优先于 `name`） |
| `name_en` | string | 否 | 英文环境名称 |
| `path` | string | 是 | 可执行文件路径。可相对 tools 目录，也可绝对路径 |
| `args` | string | 否 | 命令行参数 |
| `shell` | bool | 否 | 是否通过 shell 启动，默认 `true` |
| `console` | bool | 否 | 是否显示控制台窗口，默认 `false` |
| `cwd` | string | 否 | 工作目录，相对于 tools 目录 |
| `env` | object | 否 | 环境变量，如 `{"KEY": "value"}` |
| `multiple` | bool | 否 | 是否允许多实例，默认 `true` |
| `wait` | bool | 否 | 是否等待程序退出，默认 `false` |
| `kill_on_exit` | bool | 否 | 退出主程序时一并关闭，默认 `false` |
| `run_as_admin` | bool | 否 | 以管理员权限运行（仅 Windows） |

### 分组参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `id` | string | 是 | 唯一标识 |
| `name` | string | 是 | 显示名称 |
| `name_en` | string | 否 | 英文名称 |
| `tools` | array | 否 | 直接工具列表 |
| `groups` | array | 否 | 子分组，可嵌套 |

---

## 常见场景

### 场景一：添加自定义工具

往工具栏添加独立工具，在 `tools` 数组中直接写：

```json
{
  "tools": [
    { "id": "vscode", "name": "VS Code", "path": "D:\\Program Files\\VS Code\\Code.exe" },
    { "id": "browser", "name": "浏览器", "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", "args": "--new-window" }
  ]
}
```

### 场景二：添加自定义工具分组

往工具栏添加一个包含多个工具的分组：

```json
{
  "groups": [
    {
      "id": "dev", "name": "开发工具",
      "tools": [
        { "id": "vscode", "name": "VS Code", "path": "C:\\Program Files\\VS Code\\Code.exe" },
        { "id": "git", "name": "Git Bash", "path": "C:\\Program Files\\Git\\git-bash.exe" }
      ]
    }
  ]
}
```

### 场景三：添加系统工具

ID 以 `system/` 开头，工具出现在系统栏：

```json
{
  "tools": [
    { "id": "system/mytool", "name": "系统工具", "path": "control.exe" }
  ]
}
```

### 场景四：添加系统工具分组

分组 ID 以 `system/` 开头，整个分组出现在系统栏：

```json
{
  "groups": [
    {
      "id": "system/网络工具",
      "name": "网络工具",
      "tools": [
        { "id": "ping", "name": "Ping 测试", "path": "cmd.exe", "args": "/k ping 8.8.8.8 -t", "console": true },
        { "id": "ipconfig", "name": "网络信息", "path": "cmd.exe", "args": "/k ipconfig /all", "console": true }
      ]
    }
  ]
}
```

### 场景五：替换已有工具

内置的记事本在 `system/common` 分组中，完整 ID 是 `system/common/notepad`。要用 Notepad++ 替换它：

```json
{
  "tools": [
    {
      "id": "system/common/notepad",
      "name": "记事本 (Notepad++)",
      "path": "D:\\Tools\\notepad++.exe"
    }
  ]
}
```

同样方式可替换任何已知完整 ID 的工具或分组。

### 场景六：管理员权限运行

```json
{
  "tools": [
    { "id": "regedit", "name": "注册表编辑器", "path": "regedit.exe", "run_as_admin": true }
  ]
}
```

---

## 内置工具列表

以下为程序自带的工具，替换时需使用完整 ID。

### Windows

```
工具栏 (tools/)
（暂无内置顶层工具）

系统栏 (system/)
├─ system/common                            常用
│   ├─ system/common/notepad                记事本
│   ├─ system/common/calc                   计算器
│   ├─ system/common/paint                  画图
│   ├─ system/common/snipping               截图工具
│   ├─ system/common/charmap                字符映射表
│   ├─ system/common/psr                    步骤记录器
│   ├─ system/common/run                    运行
│   ├─ system/common/explorer               文件资源管理器
│   └─ system/common/godmode                上帝模式
├─ system/terminal                          终端
│   ├─ system/terminal/cmd                  命令提示符
│   ├─ system/terminal/powershell           PowerShell
│   └─ system/terminal/wt                   Windows 终端
├─ system/network                           网络
│   ├─ system/network/ncpa                  网络连接
│   ├─ system/network/firewall              防火墙
│   ├─ system/network/resmon                资源监视器
│   ├─ system/network/mstsc                 远程桌面
│   └─ system/network/security              Windows 安全中心
├─ system/hardware                          硬件
│   ├─ system/hardware/sound                声音设置
│   ├─ system/hardware/mouse                鼠标设置
│   ├─ system/hardware/keyboard             键盘设置
│   └─ system/hardware/printer              打印机
└─ system/admin                             系统管理
    ├─ system/admin/info                    系统信息
    │   ├─ system/admin/info/taskmgr        任务管理器
    │   ├─ system/admin/info/msinfo32       系统信息
    │   ├─ system/admin/info/perfmon        性能监视器
    │   ├─ system/admin/info/regedit        注册表编辑器
    │   ├─ system/admin/info/control        控制面板
    │   ├─ system/admin/info/msconfig       系统配置
    │   ├─ system/admin/info/appwiz         程序和功能
    │   └─ system/admin/info/envvar         环境变量
    └─ system/admin/disk                    磁盘与设备
        ├─ system/admin/disk/devmgmt        设备管理器
        ├─ system/admin/disk/diskmgmt       磁盘管理
        ├─ system/admin/disk/services       服务
        ├─ system/admin/disk/compmgmt       计算机管理
        ├─ system/admin/disk/eventvwr       事件查看器
        ├─ system/admin/disk/lusrmgr        本地用户和组
        └─ system/admin/disk/taskschd       任务计划器
```

### Linux

分组结构与 Windows 相同，工具 ID 不同：

```
系统栏 (system/)
├─ system/common                            常用
│   ├─ system/common/editor                 文本编辑器
│   ├─ system/common/calc                   计算器
│   ├─ system/common/screenshot             截图
│   ├─ system/common/charmap                字符映射表
│   ├─ system/common/filemgr                文件管理器
│   └─ system/common/sysmon                 系统监视器
├─ system/terminal                          终端
│   ├─ system/terminal/gnome-term           GNOME 终端
│   ├─ system/terminal/xterm                Xterm
│   └─ system/terminal/bash                 Bash
├─ system/network                           网络
│   ├─ system/network/nm                    网络连接
│   ├─ system/network/htop                  资源监视器
│   ├─ system/network/remmina               远程桌面
│   └─ system/network/gufw                  防火墙配置
├─ system/hardware                          硬件
│   ├─ system/hardware/sound                声音设置
│   ├─ system/hardware/disks                磁盘管理
│   ├─ system/hardware/lspci                设备列表
│   ├─ system/hardware/lsusb                USB 设备
│   └─ system/hardware/printer              打印机
└─ system/admin                             系统管理
    ├─ system/admin/info                    系统信息
    │   ├─ system/admin/info/settings       系统设置
    │   ├─ system/admin/info/users          用户管理
    │   ├─ system/admin/info/software       软件管理
    │   └─ system/admin/info/dconf          配置编辑器
    └─ system/admin/disk                    磁盘与设备
        ├─ system/admin/disk/logs           系统日志
        ├─ system/admin/disk/gparted        分区编辑器
        └─ system/admin/disk/baobab         磁盘使用分析
```
