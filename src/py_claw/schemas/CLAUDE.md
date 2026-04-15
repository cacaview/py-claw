[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **schemas**

# schemas

## 模块职责

统一定义 Python 版 Claude Code 运行时所需的协议模型，包括控制请求/响应、SDK 消息、Hook 输入输出、权限结果和 MCP 相关结构。

## 入口与启动

无独立启动入口；作为其他模块的基础模型库被导入。

## 对外接口

- `control.py`：定义 `SDKControlRequest` 联合类型、request/response envelope、settings source、MCP request、elicitation request 等
- `common.py`：定义 `PermissionMode`、`PermissionResult*`、`McpServerStatusModel`、Hook 输入/输出、`SDKMessage` 联合类型等

## 关键依赖与配置

- 基础依赖：Pydantic v2
- 通过 alias 保持 JSON 协议字段兼容，如 `schema` -> `schema_`、`async` -> `async_`

## 数据模型

本目录即数据模型本身。高信号模型包括：

- `SDKControlInitializeRequest/Response`
- `SDKControlPermissionRequest`
- `SDKControlGetSettingsResponse`
- `PermissionRuleValue`
- `PermissionResultAllow/PermissionResultDeny`
- `McpServerStatusModel`
- 多种 Hook 输入与 HookSpecificOutput

## 测试与质量

- 已看到大量 schema 接受性测试
- 覆盖重点在 union 兼容、alias 兼容、扩展字段兼容和复杂嵌套结构接受性
- 缺口：尚未看到 schema 文档自动生成或 JSON Schema 导出测试

## 常见问题 (FAQ)

### 为什么模型很多？
因为目标是贴近 Claude Code SDK/CLI 的消息面，协议面天然较宽。

### 这里更像领域模型还是传输模型？
更偏传输模型与协议模型。

## 相关文件清单

- `control.py`
- `common.py`
- `__init__.py`

## 变更记录 (Changelog)

- 2026-04-08 18:07:18：创建 `schemas` 模块文档。