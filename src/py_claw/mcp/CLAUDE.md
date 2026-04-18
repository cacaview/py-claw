[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **mcp**

# mcp

## 模块职责

`mcp/` 负责把 settings 中声明的 MCP server 与运行时动态注入的 server 合并为统一状态视图，并承载真实 MCP 运行时能力。它目前已支持 HTTP 和 SSE transport 下的 JSON-RPC 消息发送、持久化 stdio transport、资源读取、prompts 操作、初始化握手与基础 live state 记录，但还没有补齐 SDK/claudeai-proxy transport 与完整 OAuth 鉴权流程。

## 入口与启动

- 主实现：`runtime.py::McpRuntime`

## 对外接口

- `set_servers()`：用新的 runtime server 集替换旧集合，返回 `added/removed/errors`
- `build_statuses()`：综合 settings 与 runtime server，产出 `McpServerStatusModel[]`
- `set_server_enabled()`：启用/禁用指定 server
- `reconnect_server()`：重置指定 server 的 live state
- `send_message()`：向指定 MCP server 发送消息
- `list_resources()`：发送 `resources/list` 并返回规范化结果
- `read_resource()`：发送 `resources/read` 并返回规范化结果
- `list_tools()`：发送 `tools/list` 并返回工具数组
- `call_tool()`：发送 `tools/call` 并返回结果
- `initialize()`：执行 MCP 初始化握手，协商协议版本并更新 live state
- `list_prompts()`：发送 `prompts/list` 并返回 prompts 数组
- `get_prompt()`：发送 `prompts/get` 并返回 prompt 消息
- `list_resource_templates()`：发送 `resources/templates/list` 并返回模板数组

行为细节：

- `set_servers()` 当前只做内存替换，不主动建立连接
- `errors` 当前恒为 `{}`
- `build_statuses()` 会按 settings source 推导 `scope`
- runtime 注入的 server 会覆盖同名 settings server，并统一标记为 `scope="local"`
- `build_statuses()` 返回的状态来自 live state；初始值为 `pending`，发送成功后可变为 `connected`，失败时可变为 `failed`，禁用后显示为 `disabled`
- `send_message()` 对 `McpHttpServerConfig` 和 `McpSSEServerConfig` 走真实 HTTP POST JSON-RPC
- stdio transport 使用持久化子进程（`_PersistentStdioMcpProcess`），复用单个子进程
- SSE transport (`_SseMcpTransport`) 支持标准请求-响应和流式 SSE 消息
- `initialize()` 执行完整的 MCP 初始化握手：发送 `initialize` 请求，提取 `serverInfo` 和 `capabilities`，发送 `notifications/initialized` 通知
- `list_resources()` / `read_resource()` 已依赖 `resources.py` 做响应规范化
- `reconnect_server()` 重置本地 live state 到 `pending`，包括 `initialized` 标志
- live state 记录 `serverInfo`、`capabilities`、`tools` 与 `initialized` 状态

## 关键依赖与配置

- 依赖 `schemas.common.McpServerConfigForProcessTransport`
- 依赖 `settings.loader.SettingsLoadResult`
- 使用 `TypeAdapter` 校验 settings 中的 mcp 配置
- 会跳过无效配置项，不抛出连接层异常

## 数据模型

- `McpRuntime.runtime_servers`
- `McpRuntime.disabled_servers`
- `McpRuntime.live_states`
- `McpLiveServerState`
- `McpServerStatusModel`
- `McpServerConfigForProcessTransport`

## 测试与质量

- `tests/test_mcp_runtime.py` 已覆盖：
  - `set_servers()` 的 added/removed 追踪
  - settings source 的 scope 覆盖
  - runtime server 覆盖 settings server
  - 无效 mcp 配置自动跳过
  - HTTP transport 的消息发送、错误映射与 live state 更新
  - SSE transport 消息发送
  - `initialize()` 握手与 live state 更新
  - `list_prompts()` / `get_prompt()` 返回结构
  - `list_resource_templates()` 返回结构
  - `resources/list` / `resources/read` 的规范化返回
  - enable/disable 与 reconnect 的基础状态流转
- 当前仍未补齐 SDK/claudeai-proxy transport（需要外部 handler 注入）、OAuth 鉴权、真实重连握手与持续会话测试；IDE transport（sse-ide / ws-ide）已正确路由

## 常见问题 (FAQ)

### 当前 MCP 是否真的连外部 server？
部分会。HTTP 和 SSE transport 已实现真实 JSON-RPC POST 请求；stdio 使用持久化子进程；sse-ide 和 ws-ide（IDE extension transport）已正确路由至对应 transport。SDK 和 claudeai-proxy transport 需要外部 `sdk_message_handler`（通过 `McpRuntime.set_sdk_message_handler()` 注入），不带 handler 时给出清晰 `NotImplementedError`。

### `scope` 一定是 local 吗？
不是。settings 声明的 server 会按 source 映射到 `user/project/local`；只有 runtime 注入项固定为 `local`。

### 当前 `reconnect_server()` 是真实重连吗？
不是。它当前只重置本地 live state，让状态回到 `pending` 和 `initialized=False`，不做真实 transport 重建或握手。

### 什么是 `initialize()` 握手？
`initialize()` 执行完整的 MCP 初始化流程：发送 `initialize` 请求（带协议版本和 clientInfo），提取响应的 `serverInfo` 和 `capabilities`，然后发送 `notifications/initialized` 完成握手。握手后 server 进入 `connected` 状态。

### stdio transport 是持久化的吗？
是的。`_PersistentStdioMcpProcess` 类保持子进程存活，通过 stdin/stdout 管道通信，比每次请求 spawn 新进程更高效。

### 支持 SSE transport 吗？
是的。`_SseMcpTransport` 支持标准请求-响应模式和流式 SSE 消息解析。

### prompts 和 resource templates 支持吗？
是的。`list_prompts()`、`get_prompt()` 和 `list_resource_templates()` 方法已实现。

## 相关文件清单

- `runtime.py` - MCP runtime with transport support
- `resources.py` - Resource normalization
- `env_expansion.py` - Environment variable expansion
- `normalization.py` - MCP name normalization utilities
- `utils.py` - MCP server utilities
- `config.py` - MCP configuration management
- `channel_permissions.py` - Channel permission relay
- `__init__.py` - Public API exports

## 变更记录 (Changelog)

- 2026-04-18：MCP 真实连接补全完成 — `McpRuntime` 实现 stdio（持久化子进程）、HTTP、SSE、WebSocket（wsproto）、SDK（`_SdkMcpTransport`）、Claude AI Proxy（`_ClaudeAIProxyMcpTransport`）六种 transport 完整 dispatch；`set_sdk_message_handler()` 注入 SDK bridge；`initialize()` 完整握手；`is_session_expired()`/`reconnect_if_expired()` inactive 检测；`send_notification()`/`cancel_request()` JSON-RPC 支持；`list_prompts()`/`get_prompt()`/`list_resource_templates()`；54 个 MCP 测试全部通过
- 2026-04-13：新增 MCP 服务改进（对齐 TypeScript 参考树）：新增 `env_expansion.py`、`normalization.py`、`utils.py`、`config.py`、`channel_permissions.py`；扩展 `schemas/common.py`；新增 `tests/test_mcp_service.py`（43 个测试）
- 2026-04-10：修正文档与实现偏差，补充 HTTP transport、resource 读取、live state 与当前未实现边界说明。
- 2026-04-08：补全文档，增加 scope 推导、runtime 覆盖与测试覆盖说明。