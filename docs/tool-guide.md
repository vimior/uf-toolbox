# Custom Tool Configuration Guide

UF Toolbox manages custom tools in the toolbar via JSON configuration files. Add your own program shortcuts, or override built-in system tools.

---

## Configuration File

The tool path can be changed in Settings → Configuration. The default is the `tools/` folder under the software directory. Create a `tools.json` inside that folder — the program scans and loads it automatically on startup or when opening the tools menu. Structure:

```json
{
  "tools": [ ... ]
}
```

The root object contains a single `tools` array. Each entry can be a tool or a group. See below for parameters and usage.

---

## Tool ID & Menu Bar

Whether a tool appears in the "Toolbar" or "System Bar" is determined by its ID prefix:

| ID Example | Menu Bar |
|---------|-----------|
| `vscode` | Toolbar |
| `system/xxx` | System Bar |
| `system/common/notepad` | System Bar > Common |

IDs without `/` default to the Toolbar.

---

## File Format

**Only one container: `tools`.** An entry with nested `tools` is a group; without is a tool. Groups can be nested infinitely via `tools`.

---

## Tool Parameters

| Parameter | Type | Required | Description |
|------|------|:---:|------|
| `id` | string | Yes | Unique identifier. Full ID = `parent_path/id` (e.g. `system/common/notepad`). Later entries with the same full ID override earlier ones |
| `name` | string | Yes | Display name |
| `name_zh` | string | No | Chinese name (takes priority over `name`) |
| `name_en` | string | No | English name |
| `path` | string | Yes | Executable path. Relative to tools directory, or absolute |
| `args` | string | No | Command-line arguments |
| `shell` | bool | No | Launch via shell, default `true` |
| `console` | bool | No | Show console window, default `false` |
| `cwd` | string | No | Working directory, relative to tools directory |
| `env` | object | No | Environment variables, e.g. `{"KEY": "value"}` |
| `multiple` | bool | No | Allow multiple instances, default `true` |
| `wait` | bool | No | Wait for process to exit, default `false` |
| `kill_on_exit` | bool | No | Kill process when app exits, default `false` |
| `run_as_admin` | bool | No | Run as administrator (Windows only) |
| `ignore` | bool | No | Set to `true` to skip this entry, default `false` |

Group entries also support `id`, `name`, `name_zh`, `name_en`, `ignore`, `tools`.

---

## Common Scenarios

### Add a custom tool

```json
{
  "tools": [
    { "id": "vscode", "name": "VS Code", "path": "D:\\VS Code\\Code.exe" },
    { "id": "browser", "name": "Browser", "path": "C:\\Chrome\\chrome.exe", "args": "--new-window" }
  ]
}
```

### Add a group (sub-menu)

```json
{
  "tools": [
    {
      "id": "dev", "name": "Dev Tools",
      "tools": [
        { "id": "vscode", "name": "VS Code", "path": "C:\\VS Code\\Code.exe" },
        { "id": "git", "name": "Git Bash", "path": "C:\\Git\\git-bash.exe", "console": true }
      ]
    }
  ]
}
```

### Add a system tool

Prefix the ID with `system/` to place it in the System Bar:

```json
{
  "tools": [
    { "id": "system/mytool", "name": "My System Tool", "path": "control.exe" }
  ]
}
```

### Create "Run + Run as Admin" sub-menu

Nest the tool in a group with two entries — the second with `run_as_admin: true`:

```json
{
  "tools": [
    {
      "id": "regedit", "name": "Registry Editor",
      "tools": [
        { "id": "run", "name": "Run", "path": "regedit.exe" },
        { "id": "admin", "name": "Run as Admin", "path": "regedit.exe", "run_as_admin": true }
      ]
    }
  ]
}
```

### Override an existing tool

The built-in Notepad has full ID `system/common/notepad`. Replace it with Notepad++:

```json
{
  "tools": [
    {
      "id": "system/common/notepad",
      "name": "Notepad (Notepad++)",
      "path": "D:\\Tools\\notepad++.exe"
    }
  ]
}
```

---

## Built-in Tools (Windows)

```
System Bar (system/)
├─ system/common                              Common
│   ├─ system/common/notepad                  Notepad
│   ├─ system/common/calc                     Calculator
│   ├─ system/common/paint                    Paint
│   ├─ system/common/snipping                 Snipping Tool
│   ├─ system/common/charmap                  Character Map
│   ├─ system/common/psr                      Steps Recorder
│   ├─ system/common/run                      Run
│   ├─ system/common/explorer                 File Explorer
│   └─ system/common/godmode                  God Mode
├─ system/terminal                            Terminals
│   ├─ system/terminal/cmd                    Command Prompt
│   │   ├─ system/terminal/cmd/cmd             Run
│   │   └─ system/terminal/cmd/cmd_admin       Run as Admin
│   ├─ system/terminal/powershell             PowerShell
│   │   ├─ …/powershell/powershell             Run
│   │   └─ …/powershell/powershell_admin       Run as Admin
│   └─ system/terminal/wt                     Windows Terminal
│       ├─ system/terminal/wt/wt               Run
│       └─ system/terminal/wt/wt_admin         Run as Admin
├─ system/network                             Network
│   ├─ system/network/ncpa                    Network Connections
│   ├─ system/network/firewall                Firewall
│   ├─ system/network/resmon                  Resource Monitor
│   ├─ system/network/mstsc                   Remote Desktop
│   └─ system/network/security                Windows Security
├─ system/hardware                            Hardware
│   ├─ system/hardware/sound                  Sound
│   ├─ system/hardware/mouse                  Mouse
│   ├─ system/hardware/keyboard               Keyboard
│   └─ system/hardware/printer                Printers
└─ system/admin                               Administration
    ├─ system/admin/info                      System Info
    │   ├─ system/admin/info/taskmgr           Task Manager
    │   ├─ system/admin/info/msinfo32          System Information
    │   ├─ system/admin/info/perfmon           Performance Monitor
    │   ├─ system/admin/info/control           Control Panel
    │   ├─ system/admin/info/msconfig          System Configuration
    │   ├─ system/admin/info/appwiz            Programs & Features
    │   └─ system/admin/info/envvar            Environment Variables
    └─ system/admin/management                 Management
        ├─ system/admin/management/diskmgmt    Disk Management
        │   ├─ …/diskmgmt/diskmgmt             Run
        │   └─ …/diskmgmt/diskmgmt_admin       Run as Admin
        ├─ system/admin/management/eventvwr    Event Viewer
        │   ├─ …/eventvwr/eventvwr             Run
        │   └─ …/eventvwr/eventvwr_admin       Run as Admin
        ├─ system/admin/management/taskschd    Task Scheduler
        │   ├─ …/taskschd/taskschd             Run
        │   └─ …/taskschd/taskschd_admin       Run as Admin
        ├─ system/admin/management/devmgmt     Device Manager
        │   ├─ …/devmgmt/devmgmt               Run
        │   └─ …/devmgmt/devmgmt_admin         Run as Admin
        ├─ system/admin/management/services    Services
        │   ├─ …/services/services             Run
        │   └─ …/services/services_admin       Run as Admin
        ├─ system/admin/management/compmgmt    Computer Management
        │   ├─ …/compmgmt/compmgmt             Run
        │   └─ …/compmgmt/compmgmt_admin       Run as Admin
        ├─ system/admin/management/lusrmgr     Local Users & Groups
        │   ├─ …/lusrmgr/lusrmgr               Run
        │   └─ …/lusrmgr/lusrmgr_admin         Run as Admin
        └─ system/admin/management/regedit     Registry Editor
            ├─ …/regedit/regedit               Run
            └─ …/regedit/regedit_admin          Run as Admin
```

---

## Built-in Tools (Linux)

Same group structure as Windows, with different tools:

```
System Bar (system/)
├─ system/common                              Common
│   ├─ system/common/editor                   Text Editor
│   ├─ system/common/calc                     Calculator
│   ├─ system/common/screenshot               Screenshot
│   ├─ system/common/charmap                  Character Map
│   ├─ system/common/filemgr                  File Manager
│   └─ system/common/sysmon                   System Monitor
├─ system/terminal                            Terminals
│   ├─ system/terminal/gnome-term             GNOME Terminal
│   ├─ system/terminal/xterm                  Xterm
│   └─ system/terminal/bash                   Bash
├─ system/network                             Network
│   ├─ system/network/nm                      Network Connections
│   ├─ system/network/htop                    Resource Monitor
│   ├─ system/network/remmina                 Remote Desktop
│   └─ system/network/gufw                    Firewall Config
├─ system/hardware                            Hardware
│   ├─ system/hardware/sound                  Sound Settings
│   ├─ system/hardware/lspci                  Device List
│   ├─ system/hardware/lsusb                  USB Devices
│   └─ system/hardware/printer                Printers
└─ system/admin                               Administration
    ├─ system/admin/info                      System Info
    │   ├─ system/admin/info/settings          Settings
    │   ├─ system/admin/info/users             User Management
    │   ├─ system/admin/info/software          Software Manager
    │   └─ system/admin/info/dconf             Configuration Editor
    └─ system/admin/management                 Management
        ├─ system/admin/management/disks       Disk Management
        ├─ system/admin/management/gparted     Partition Editor
        ├─ system/admin/management/logs        System Logs
        └─ system/admin/management/baobab      Disk Usage Analyzer
```
