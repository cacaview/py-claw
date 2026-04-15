[根目录](../CLAUDE.md) > **tests**

# tests

## 模块职责

`tests/` 是 Python 主实现的 pytest 回归测试目录，当前覆盖协议兼容、控制循环、权限规则、工具运行时、hook 执行链和 MCP 状态建模。

## 入口与启动

- 运行方式：`pytest`
- 根配置：`../pyproject.toml` 中的 `[tool.pytest.ini_options]`
- 测试引导：`conftest.py` 把 `src/` 注入 `sys.path`

## 对外接口

该目录不暴露运行时接口；它通过断言约束以下对外行为：

- `py_claw.cli.main.main`
- `py_claw.cli.structured_io.StructuredIO`
- `py_claw.cli.control.ControlRuntime`
- `py_claw.tools.ToolRuntime`
- `py_claw.hooks.runtime.HookRuntime`
- `py_claw.mcp.runtime.McpRuntime`
- `py_claw.permissions.*`
- `py_claw.schemas.*`

## 关键依赖与配置

- `pytest`
- `pydantic.TypeAdapter`
- 临时目录/临时设置文件用于验证来源优先级
- `conftest.py` 通过 `sys.path.insert(0, str(SRC))` 让测试直接导入 `src/py_claw`

## 数据模型

无数据库模型；覆盖的是控制协议、Hook 输出、权限 rule、MCP 配置、工具输入输出等结构模型。

## 测试与质量

已扫描文件：

- `test_cli_and_schemas.py`
- `test_cli_control_runtime.py`
- `test_tools_runtime.py`
- `test_hooks_runtime.py`
- `test_mcp_runtime.py`
- `conftest.py`

主要测试主题：

- CLI 参数、stream-json、response envelope
- settings merge 与来源优先级
- permission rule precedence
- 内置工具注册与本地执行
- 任务工具 CRUD、依赖关系、删除语义
- 后台 Bash 生命周期、日志文件、阻塞/非阻塞 `TaskOutput`、`TaskStop`
- `stop_task` 控制请求与共享 `TaskRuntime`
- hook 输入改写、放行、拒绝后副作用、失败回调
- MCP server added/removed、scope 推导与 runtime 覆盖

## 常见问题 (FAQ)

### 测试更偏单元还是集成？
当前以单元测试和轻集成为主，重点是协议形状、规则语义与本地运行时行为。

### 是否有真实 MCP/子进程测试？
没有真实 MCP 连接测试；但已经有 shell 命令 hook、本地 Bash 工具、后台子进程任务、任务停止与输出读取链路的执行测试。

## 相关文件清单

- `conftest.py`
- `test_cli_and_schemas.py`
- `test_cli_control_runtime.py`
- `test_tools_runtime.py`
- `test_hooks_runtime.py`
- `test_mcp_runtime.py`

## 变更记录 (Changelog)

- 2026-04-08：补全文档，纳入 tools/hooks/mcp 测试与 `conftest.py`。