[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **services/lsp**

# services/lsp

## 模块职责

`services/lsp/` 提供 LSP (Language Server Protocol) 服务层，负责：

- LSP stdio JSON-RPC 客户端通信
- 多 server 生命周期管理（懒启动/停止/重启）
- 按文件扩展名路由到对应 LSP server
- 文档生命周期同步（didOpen/didChange/didSave/didClose）
- Diagnostics 注册表管理（跨版本去重、batch 限流）
- 从 settings 加载 LSP server 配置

## 入口与启动

- LSP client：`client.py::LSPClient`
- Server 实例管理：`server.py::LSPServerInstance`
- 多 server 路由：`manager.py::LSPServerManager`
- Diagnostics 注册表：`diagnostics.py::LSPDiagnosticRegistry`
- 配置加载：`config.py::load_lsp_configs_from_settings`
- 内置配置：`config.py::BUILTIN_LSP_CONFIGS`
- LSP 工具：`tools/lsp_tool.py::LSPTool`

## 对外接口

### LSPClient

- `start()` — 启动 subprocess 并初始化 LSP handshake
- `initialize()` — 发送 `initialize` 请求，获取 server capabilities
- `send_request()` — 发送 JSON-RPC 请求并等待响应
- `send_notification()` — 发送 JSON-RPC notification（无响应）
- `on_notification()` — 注册 notification 处理器
- `on_request()` — 注册 request 处理器
- `stop()` — 优雅关闭 server

### LSPServerManager

- `get_server_for_file()` — 按文件扩展名查找对应 server
- `register_servers()` — 注册多个 server 配置
- `start_server()` — 启动单个 server（懒启动）
- `stop_server()` — 停止 server
- `restart_server()` — 重启 server

### LSPDiagnosticRegistry

- `add()` — 添加 diagnostics（自动去重、batch 限流）
- `get_for_file()` — 获取文件的 diagnostics
- `clear_old_entries()` — 清理旧 entries

## 内置 LSP Server 配置

| Server | 文件扩展名 | Command |
|---|---|---|
| `pylsp` | .py | `pylsp` |
| `typescript-language-server` | .ts, .tsx, .js, .jsx | `typescript-language-server --stdio` |
| `rust-analyzer` | .rs | `rust-analyzer` |
| `gopls` | .go | `gopls` |
| `solargraph` | .rb | `solargraph` |
| `typescript-language-server` | .js, .jsx | `typescript-language-server --stdio` |

## LSP 工具操作

`tools/lsp_tool.py` 暴露 8 种 LSP 操作：

- `goToDefinition` — 跳转到符号定义
- `findReferences` — 查找符号引用
- `hover` — 获取 hover 信息
- `documentSymbol` — 列出文档符号
- `workspaceSymbol` — 跨文件搜索符号
- `goToImplementation` — 跳转到实现
- `incomingCalls` — 呼入调用
- `outgoingCalls` — 呼出调用

## 数据模型

- `LSPDiagnostic` — diagnostic 信息
- `LSPRange` / `LSPPosition` — 位置范围
- `ScopedLspServerConfig` — 带 scope 的 server 配置
- `PendingLSPDiagnostic` — 待处理的 diagnostic

## 测试与质量

- `tests/test_lsp_runtime.py` — 11 个单元测试
- 覆盖 diagnostic registry、server manager、config loading

## 常见问题 (FAQ)

### 为什么需要 LSP tool？
LSP tool 把 LSP server 的能力通过工具接口暴露给模型，使模型可以查询代码定义、引用、hover 信息等。

### LSP server 需要手动安装吗？
是的。Python 不自带 LSP server，用户需根据语言安装对应的 LSP server（如 `pip install python-lsp-server`）。

## 相关文件清单

- `client.py`
- `server.py`
- `manager.py`
- `diagnostics.py`
- `config.py`
- `types.py`
- `__init__.py`
- `tools/lsp_tool.py`

## 变更记录 (Changelog)

- 2026-04-12：新增 LSP 服务层文档。