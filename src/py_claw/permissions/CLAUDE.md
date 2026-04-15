[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **permissions**

# permissions

## 模块职责

将 settings 中的权限配置转化为可执行规则，并对工具调用目标执行 `allow / ask / deny` 判定。

## 入口与启动

- 求值入口：`engine.py::PermissionEngine.evaluate`
- 上下文构建：`state.py::build_permission_context`
- 规则解析/匹配：`rules.py`

## 对外接口

- 支持规则行为：`allow`、`deny`、`ask`
- 支持模式：`default`、`acceptEdits`、`bypassPermissions`、`plan`、`dontAsk`
- 支持规则类型：
  - 工具级规则，如 `Read`
  - 文件/内容模式，如 `Read(src/**/*.py)`
  - Bash 前缀规则，如 `Bash(pytest:*)`
  - MCP server/tool 规则，如 `mcp__docs`、`mcp__docs__*`

## 关键依赖与配置

- 依赖 `settings.loader.SettingsLoadResult`
- 规则优先级：先 `deny`，再 `ask`，再模式短路，再 `allow`，最后默认 ask
- source 顺序：`userSettings -> projectSettings -> localSettings -> flagSettings -> policySettings -> cliArg -> command -> session`
- 若启用 `allowManagedPermissionRulesOnly`，仅保留 `policySettings` 规则

## 数据模型

- `PermissionEvaluation`
- `PermissionContext`
- `PermissionRule`
- `PermissionTarget`

## 测试与质量

- 这是当前仓库测试最密集的区域之一
- 已覆盖：source 顺序、模式覆盖、bypass 禁用、managed-only、glob 匹配、MCP 匹配、Bash 前缀、规则 round-trip、reason 保留
- 缺口：未见性能测试；大规则集下的匹配成本尚未评估

## 常见问题 (FAQ)

### 为什么 `ask` 在 `allow` 之前？
因为显式 ask/deny 需要覆盖默认模式与更宽松规则。

### `dontAsk` 会发生什么？
会把 ask 结果最终收敛为 deny，reason 为 `mode`。

## 相关文件清单

- `engine.py`
- `state.py`
- `rules.py`
- `__init__.py`

## 变更记录 (Changelog)

- 2026-04-08 18:07:18：创建 `permissions` 模块文档。