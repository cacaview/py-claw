[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **hooks**

# hooks

## 模块职责

`hooks/` 不只是配置 schema。当前已经同时包含：

- Hook 配置模型与事件校验
- 命令型 hook 的本地执行运行时
- 结构化 JSON 输出解析
- 针对权限请求与工具生命周期的决策回写

## 入口与启动

- 配置模型：`schemas.py`
- 运行时入口：`runtime.py::HookRuntime`
- 设置入口：`HooksSettings.from_event_map()`

## 对外接口

已实现的工具相关事件：

- `PreToolUse`
- `PostToolUse`
- `PostToolUseFailure`
- `PermissionRequest`
- `PermissionDenied`

当前运行时只执行 `type="command"` 的 hook，并支持：

- matcher 过滤
- `if` 条件过滤
- `bash` / `powershell` shell 选择
- 解析 stdout 中的同步 JSON 结构化输出

## 关键依赖与配置

- 使用 Pydantic 建模，保留 `if`、`async` 等字段别名
- `HookRuntime` 通过 `subprocess.run()` 执行命令 hook
- shell 解析使用 `bash -lc` 或 PowerShell `-Command`
- matcher 复用权限规则解析逻辑，而不是单独发明一套 DSL

## 数据模型

- `BashCommandHook`
- `PromptHook`
- `HttpHook`
- `AgentHook`
- `HookMatcher`
- `HooksSettings`
- `HookExecutionRecord`
- `HookPermissionDecision`
- `HookDispatchResult`

## 测试与质量

- `tests/test_hooks_runtime.py` 已覆盖：
  - `PermissionRequest` hook 放行被拒工具
  - `PermissionDenied` 执行命令 hook
  - `PreToolUse` 改写工具输入
  - `PostToolUseFailure` 在工具失败后触发
- 当前缺口主要不是“没有执行器”，而是：
  - `prompt/http/agent` 类型仍以 schema 为主
  - 细项字段如 `allowedEnvVars`、`asyncRewake` 尚无系统级测试

## 常见问题 (FAQ)

### 这里会真正触发 hook 吗？
会。`runtime.py` 已实现命令型 hook 执行器，并会在工具生命周期与权限请求阶段被调用。

### 所有 hook 类型都已执行化了吗？
没有。当前确认真正执行的是 command hook；`prompt`、`http`、`agent` 仍主要停留在 schema 层。

## 相关文件清单

- `schemas.py`
- `runtime.py`
- `__init__.py`

## 变更记录 (Changelog)

- 2026-04-08：补全文档，修正“只有 schema、没有执行器”的过时结论。