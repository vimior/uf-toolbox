# 自定义工具配置指南

UF Toolbox 通过 JSON 配置文件管理工具栏中的自定义工具。你可以添加自己的程序快捷启动，或覆盖已有的系统工具。

---

## 工具 ID 与菜单栏

工具出现在"工具栏"还是"系统栏"，由 ID 前缀决定：

| ID 示例 | 所属菜单栏 |
|---------|-----------|
| `vscode` | 工具栏 |
| `system/xxx` | 系统栏 |
| `system/common/notepad` | 系统栏 > 常用 |

没有 `/` 的 ID 默认归入工具栏。

---

## 文件格式

**只有一种容器：`tools`。** 条目里嵌套了 `tools` 就是分组，没有就是工具。

```json
{
  "tools": [
    { "id": "my-tool", "name": "我的工具", "path": "notepad.exe" },

    {
      "id": "my-group", "name": "我的分组",
      "tools": [
        { "id": "vscode", "name": "VS Code", "path": "C:\\VS Code\\Code.exe" },
        { "id": "git", "name": "Git Bash", "path": "C:\\Git\\git-bash.exe" }
      ]
    }
  ]
}
```

分组内还可以继续嵌套 `tools`，无限层级。

---

## 工具参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `id` | string | 是 | 唯一标识。完整 ID = `上级路径/本id`（如 `system/common/notepad`）。后发现的同完整 ID 会覆盖之前的 |
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
| `ignore` | bool | 否 | 设为 `true` 跳过此项，默认 `false` |

分组条目同样支持 `id`、`name`、`name_zh`、`name_en`、`ignore`、`tools`。

---

## 常见场景

### 添加自定义工具

```json
{
  "tools": [
    { "id": "vscode", "name": "VS Code", "path": "D:\\VS Code\\Code.exe" },
    { "id": "browser", "name": "浏览器", "path": "C:\\Chrome\\chrome.exe", "args": "--new-window" }
  ]
}
```

### 添加分组（含子菜单）

```json
{
  "tools": [
    {
      "id": "dev", "name": "开发工具",
      "tools": [
        { "id": "vscode", "name": "VS Code", "path": "C:\\VS Code\\Code.exe" },
        { "id": "git", "name": "Git Bash", "path": "C:\\Git\\git-bash.exe", "console": true }
      ]
    }
  ]
}
```

### 添加系统工具

ID 加 `system/` 前缀即出现在系统栏：

```json
{
  "tools": [
    { "id": "system/mytool", "name": "系统工具", "path": "control.exe" }
  ]
}
```

### 创建"运行 + 管理员运行"子菜单

把工具做成嵌套分组，放两个条目——第二个加 `run_as_admin: true`：

```json
{
  "tools": [
    {
      "id": "regedit", "name": "注册表编辑器",
      "tools": [
        { "id": "run", "name": "运行", "path": "regedit.exe" },
        { "id": "admin", "name": "管理员运行", "path": "regedit.exe", "run_as_admin": true }
      ]
    }
  ]
}
```

### 替换已有工具

内置的记事本完整 ID 是 `system/common/notepad`。用 Notepad++ 替换：

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

---

## 内置工具列表（Windows）

```
系统栏 (system/)
├─ system/common                              常用
│   ├─ system/common/notepad                  记事本
│   ├─ system/common/calc                     计算器
│   ├─ system/common/paint                    画图
│   ├─ system/common/snipping                 截图工具
│   ├─ system/common/charmap                  字符映射表
│   ├─ system/common/psr                      步骤记录器
│   ├─ system/common/run                      运行
│   ├─ system/common/explorer                 文件资源管理器
│   └─ system/common/godmode                  上帝模式
├─ system/terminal                            终端
│   ├─ system/terminal/cmd                    命令提示符
│   │   ├─ system/terminal/cmd/cmd             　运行
│   │   └─ system/terminal/cmd/cmd_admin       　管理员运行
│   ├─ system/terminal/powershell             PowerShell
│   │   ├─ system/terminal/powershell/powershell          　运行
│   │   └─ system/terminal/powershell/powershell_admin    　管理员运行
│   └─ system/terminal/wt                     Windows 终端
│       ├─ system/terminal/wt/wt               　运行
│       └─ system/terminal/wt/wt_admin         　管理员运行
├─ system/network                             网络
│   ├─ system/network/ncpa                    网络连接
│   ├─ system/network/firewall                防火墙
│   ├─ system/network/resmon                  资源监视器
│   ├─ system/network/mstsc                   远程桌面
│   └─ system/network/security                Windows 安全中心
├─ system/hardware                            硬件
│   ├─ system/hardware/sound                  声音设置
│   ├─ system/hardware/mouse                  鼠标设置
│   ├─ system/hardware/keyboard               键盘设置
│   └─ system/hardware/printer                打印机
└─ system/admin                               系统管理
    ├─ system/admin/info                      系统信息
    │   ├─ system/admin/info/taskmgr           任务管理器
    │   ├─ system/admin/info/msinfo32          系统信息
    │   ├─ system/admin/info/perfmon           性能监视器
    │   ├─ system/admin/info/control           控制面板
    │   ├─ system/admin/info/msconfig          系统配置
    │   ├─ system/admin/info/appwiz            程序和功能
    │   └─ system/admin/info/envvar            环境变量
    └─ system/admin/management                 管理工具
        ├─ system/admin/management/diskmgmt    磁盘管理
        │   ├─ …/diskmgmt/diskmgmt             　运行
        │   └─ …/diskmgmt/diskmgmt_admin       　管理员运行
        ├─ system/admin/management/eventvwr    事件查看器
        │   ├─ …/eventvwr/eventvwr             　运行
        │   └─ …/eventvwr/eventvwr_admin       　管理员运行
        ├─ system/admin/management/taskschd    任务计划器
        │   ├─ …/taskschd/taskschd             　运行
        │   └─ …/taskschd/taskschd_admin       　管理员运行
        ├─ system/admin/management/devmgmt     设备管理器
        │   ├─ …/devmgmt/devmgmt               　运行
        │   └─ …/devmgmt/devmgmt_admin         　管理员运行
        ├─ system/admin/management/services    服务
        │   ├─ …/services/services             　运行
        │   └─ …/services/services_admin       　管理员运行
        ├─ system/admin/management/compmgmt    计算机管理
        │   ├─ …/compmgmt/compmgmt             　运行
        │   └─ …/compmgmt/compmgmt_admin       　管理员运行
        ├─ system/admin/management/lusrmgr     本地用户和组
        │   ├─ …/lusrmgr/lusrmgr               　运行
        │   └─ …/lusrmgr/lusrmgr_admin         　管理员运行
        └─ system/admin/management/regedit     注册表编辑器
            ├─ …/regedit/regedit               　运行
            └─ …/regedit/regedit_admin         　管理员运行
```

---

## 内置工具列表（Linux）

分组结构与 Windows 相同，仅工具内容不同：

```
系统栏 (system/)
├─ system/common                              常用
│   ├─ system/common/editor                   文本编辑器
│   ├─ system/common/calc                     计算器
│   ├─ system/common/screenshot               截图
│   ├─ system/common/charmap                  字符映射表
│   ├─ system/common/filemgr                  文件管理器
│   └─ system/common/sysmon                   系统监视器
├─ system/terminal                            终端
│   ├─ system/terminal/gnome-term             GNOME 终端
│   ├─ system/terminal/xterm                  Xterm
│   └─ system/terminal/bash                   Bash
├─ system/network                             网络
│   ├─ system/network/nm                      网络连接
│   ├─ system/network/htop                    资源监视器
│   ├─ system/network/remmina                 远程桌面
│   └─ system/network/gufw                    防火墙配置
├─ system/hardware                            硬件
│   ├─ system/hardware/sound                  声音设置
│   ├─ system/hardware/lspci                  设备列表
│   ├─ system/hardware/lsusb                  USB 设备
│   └─ system/hardware/printer                打印机
└─ system/admin                               系统管理
    ├─ system/admin/info                      系统信息
    │   ├─ system/admin/info/settings          系统设置
    │   ├─ system/admin/info/users             用户管理
    │   ├─ system/admin/info/software          软件管理
    │   └─ system/admin/info/dconf             配置编辑器
    └─ system/admin/management                 管理工具
        ├─ system/admin/management/disks       磁盘管理
        ├─ system/admin/management/gparted     分区编辑器
        ├─ system/admin/management/logs        系统日志
        └─ system/admin/management/baobab      磁盘使用分析
```
