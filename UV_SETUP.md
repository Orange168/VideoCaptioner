# UV 项目设置指南

## 安装 uv

如果还没有安装 uv，可以使用以下命令安装：

```bash
powershell -ExecutionPolicy Bypass -c "irm https://github.com/astral-sh/uv/releases/download/0.6.16/uv-installer.ps1 | iex"
```

## 项目设置

1. 创建新的虚拟环境：
```bash
uv venv
```

2. 激活虚拟环境：
```bash
# Windows
.venv/Scripts/activate

# Linux/macOS
source .venv/bin/activate
```

3. 安装依赖：
```bash
uv pip install -r requirements.txt
```

## 日常使用

- 添加新依赖：
```bash
uv pip install package_name
```

- 更新 requirements.txt：
```bash
uv pip freeze > requirements.txt
```

- 同步依赖（确保所有依赖都是最新的）：
```bash
uv pip sync requirements.txt
```

## 为什么使用 uv？

- 更快的依赖解析和安装速度
- 更好的依赖锁定机制
- 与现有的 pip 工具链完全兼容
- 更现代的包管理体验

## 测试 Gemini API

安装依赖后，可以运行测试文件：
```bash
python test_gemini.py
```

注意：运行测试前请确保已经设置了正确的 API key。 