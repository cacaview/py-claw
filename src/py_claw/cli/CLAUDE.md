[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **cli**

# cli

## 模块职责

负责命令行解析、`stream-json` 控制循环、运行态承载和控制请求分发，是 Python 主实现最接近用户入口的一层。

## 入口与启动

- 入口函数：`main.py::main`
- 参数构造：`main.py::build_parser`
- 控制循环：`main.py::_run_stream_json`
- 请求分发：`control.py::ControlRuntime.handle_request`
- 运行态：`runtime.py::RuntimeState`

## 对外接口

- CLI 参数：`--version`、`--print`、`--input-format`、`--output-format`、`--sdk-url`、`--include-partial-messages`
- `stream-json` 模式下接受 `SDKControlRequestEnvelope`，输出 `SDKControlResponseEnvelope`
- 支持的 control subtype 目前包括 `initialize`、`interrupt`、`set_permission_mode`、`set_model`、`set_max_thinking_tokens`、`apply_flag_settings`、`get_settings`、`get_context_usage`、`rewind_files`、`cancel_async_message`、`seed_read_state`、`can_use_tool`、`mcp_status`、`mcp_set_servers`、`mcp_reconnect`、`mcp_toggle`、`mcp_message`、`reload_plugins`、`elicitation`、`stop_task`

## 关键依赖与配置

- 依赖 `schemas/control.py` 做协议校验
- 依赖 `settings.loader` 与 `settings.validation`
- 依赖 `permissions.engine` 做工具权限判定
- 依赖 `tools.runtime` 提取权限目标
- 依赖 `mcp.runtime` 汇总 MCP server 状态

## 数据模型

- `RuntimeState` 保存 cwd、home_dir、permission_mode、model、flag_settings、policy_settings，以及共享的 `ToolRuntime`/`TaskRuntime`
- `StructuredIO` 跟踪 pending/completed/failed request，以及 stdout message 缓冲
- `StructuredIO` 还会在收到 `env` 控制数据时直接更新进程环境变量

## 测试与质量

- 高覆盖点：参数错误组合、initialize 流、prompt prepend、interrupt、settings 返回、权限返回形状
- 缺口：没有真实 stdout/stderr 之外的交互式终端或子进程测试

## 常见问题 (FAQ)

### 当前 CLI 会真正执行任务吗？
它仍更像控制协议 runtime，而不是完整 agent 执行器；但已经可以联动工具运行时与任务运行时，支持诸如 `rewind_files`、`seed_read_state`、`stop_task` 等控制请求。

### `StructuredIO` 的重点是什么？
重点是按行解析、区分控制消息/用户消息、跟踪 pending request、处理 keep_alive 与环境变量更新。

### `mcp_message` 当前支持吗？
还不支持。控制层会显式返回 “MCP transport is not implemented” 错误，而不是尝试转发真实 MCP 消息。

## 相关文件清单

- `main.py`
- `control.py`
- `runtime.py`
- `structured_io.py`
- `transports/` - Transport implementations for remote sessions
  - `base.py` - Base Transport interface
  - `websocket.py` - WebSocket transport with auto-reconnect

## 变更记录 (Changelog)

- 2026-04-14：新增 `transports/` 模块，实现 CLI 远程会话传输层
- 2026-04-08 18:07:18：创建 `cli` 模块文档。