# UFACTORY Toolbox

UFACTORY 实用工具集合。

## 环境要求

- Python >= 3.10

## 安装

```bash
# 创建 conda 环境
conda create -n uf-toolbox python=3.10 -y

# 激活环境
conda activate uf-toolbox

# 安装项目（开发模式）
pip install -e ".[dev]"
```

## 使用

```bash
uf-toolbox
```

## 功能

### 菜单栏

- **设置** — 外观主题切换（浅色/深色）、语言切换（中文/English/自动）、日志查看、**配置**
- **系统** — 系统类工具（可通过工具配置归类）
- **工具** — 通用工具（自动扫描工具目录下的可执行文件及 `tools.json` 配置）
- **插件** — 动态加载插件，支持独立窗口运行

### 配置（设置 → 配置）

- **工具路径** — 指定工具扫描目录，默认为 `tools`，可通过文件夹选择器修改
- **插件路径** — 指定插件加载目录，默认为 `plugins`
- 修改后保存按钮激活，关闭窗口时如有未保存修改会弹窗提醒

### 打包

使用 PyInstaller 打包为独立可执行文件：

```bash
pyinstaller uf_toolbox.spec --clean
```
