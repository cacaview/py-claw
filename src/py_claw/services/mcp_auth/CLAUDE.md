[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > [services](../CLAUDE.md) > **mcp_auth**

# mcp_auth

## 模块职责

`mcp_auth/` 提供 MCP-specific OAuth/鉴权链，支持：

- OAuth 2.0 + PKCE 授权码流程
- Token 存储与刷新
- XAA (Cross-App Access) 支持
- VSCode SDK MCP 集成
- Channel 权限与通知（Discord/Telegram/iMessage 等）
- Elicitation 请求处理
- Official MCP registry 验证

## 子模块

- `types.py` — OAuth token/settings/config 类型定义
- `service.py` — 核心 OAuth 服务（SecureStorage、McpAuthProvider、OAuthCallbackServer、McpAuthService）
- `vscode.py` — VSCode SDK MCP 集成（McpAuthTool）
- `xaa.py` — XAA token exchange（RFC 8693 + RFC 7523）
- `channel.py` — Channel 权限回调、gate 和消息包装
- `elicitation.py` — MCP elicitation 请求处理器
- `registry.py` — Official MCP registry URL 验证

## 关键接口

### OAuth Flow
- `McpAuthService.perform_oauth_flow()` — 执行 OAuth 授权码流程
- `McpAuthService.refresh_server_tokens()` — 刷新过期的 token
- `OAuthCallbackServer` — 本地 HTTP server 接收 OAuth callback

### XAA (Cross-App Access)
- `perform_xaa_auth()` — 执行 XAA auth flow
- `perform_xaa_token_exchange()` — RFC 8693 token exchange
- `is_xaa_enabled()` — 检查 XAA 是否启用

### Channel Permissions
- `ChannelPermissionCallbacks` — permission relay 回调
- `gate_channel_server()` — channel server gate 检查
- `filter_permission_relay_clients()` — 过滤可 relay 权限的 MCP clients
- `short_request_id()` — 生成短 ID 用于 permission reply

### Elicitation
- `ElicitationHandler` — 队列管理 elicitation 请求
- `ElicitationRequestEvent` — pending elicitation 事件

### Registry
- `is_official_mcp_url()` — 检查 URL 是否在 official registry
- `prefetch_official_mcp_urls()` — 异步预取 registry URLs

## 变更记录 (Changelog)

- 2026-04-13：补全 mcp_auth 模块（MCP OAuth、XAA、VSCode SDK、channel 权限、elicitation、registry）
