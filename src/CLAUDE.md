[根目录](../CLAUDE.md) > **src**

# src

## 模块职责

`src/` 是 Python 主实现源码根目录，当前实际业务包为 `py_claw/`。这里不是多包 workspace，而是单包源码入口。

## 入口与启动

- 主入口：`py_claw/cli/main.py`
- 包版本：`py_claw/__init__.py`
- 新增运行时子域：`py_claw/query/`

## 对外接口

- CLI 入口通过 `pyproject.toml` 暴露 `py-claw = py_claw.cli.main:main`
- 结构化控制协议与消息模型主要在 `py_claw/schemas/`
- query runtime、工具执行、hook 运行时、MCP 状态快照均位于 `py_claw/` 包内

## 关键依赖与配置

- 根配置：`../pyproject.toml`
- 关键依赖：`pydantic>=2.8,<3`
- 测试框架：`pytest>=8,<9`

## 数据模型

无持久化数据库模型；“数据模型”主要指 SDK 控制消息、权限规则、settings schema、hook 输出、MCP server 状态结构与 query turn 结构。

## 测试与质量

- 测试目录：`../tests/`
- 当前扫描已覆盖 Python 主实现的大部分高信号文件
- 运行态核心除了各子包，还应包含独立的 `py_claw/tasks.py` 与 `py_claw/query/`：前者承载任务列表、后台 shell 任务、日志文件与阻塞/非阻塞输出读取；后者承载 turn 编排与后端适配
- 主要剩余缺口已不再是核心执行路径，而是少量边缘导出文件与尚未单独建页的主题

## 常见问题 (FAQ)

### 这是多包仓库吗？
不是。`src/` 当前只有一个主 Python 包 `py_claw`。

### `ClaudeCode-main/` 和这里是什么关系？
`src/` 是当前主实现；`ClaudeCode-main/` 是上游 TypeScript 参考镜像，用于协议和架构对齐。

## 相关文件清单

- `py_claw/cli/main.py`
- `py_claw/cli/control.py`
- `py_claw/tasks.py`
- `py_claw/query/CLAUDE.md`
- `py_claw/query/backend.py`
- `py_claw/query/engine.py`
- `py_claw/tools/runtime.py`
- `py_claw/hooks/runtime.py`
- `py_claw/mcp/runtime.py`
- `py_claw/schemas/control.py`
- `py_claw/settings/loader.py`
- `py_claw/permissions/engine.py`

## 变更记录 (Changelog)

- 2026-04-11：补全文档，修正 Python 主实现覆盖面说明，并纳入 query runtime 子域。
