# UFACTORY Toolbox

UFACTORY 实用工具集合。

## 环境要求

- Python >= 3.10

## 安装

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 安装项目（开发模式）
pip install -e ".[dev]"
```

## 使用

```bash
uf-toolbox
```

## 开发

```bash
# 运行测试
pytest

# 代码检查
ruff check src/

# 类型检查
mypy src/
```
