[根目录](../../../CLAUDE.md) > [src](../CLAUDE.md) > **py_claw/query**

# py_claw/query

## 模块职责

`py_claw/query/` 是 Python 主实现中的 query runtime 层，负责把上层控制循环准备好的 turn 组织成可执行结构，并通过 backend / executor 抽象完成一次查询轮次。同时负责 turn 后的 stop hook 分发、budget 检查和自动 compact 触发。

## 入口与启动

- 后端适配：`backend.py`
- turn 编排：`engine.py`
- stop hook 分发：`stop_hooks.py`
- 包导出：`__init__.py`

## 对外接口

### 后端抽象

`backend.py` 提供：

- `QueryBackend`
- `BackendTurnResult`
- `BackendToolCall`
- `PlaceholderQueryBackend`（未配置后端时的回退）
- `SdkUrlQueryBackend`
- `AnthropicQueryBackend`（Anthropic 协议，真实模型调用）
- `ApiQueryBackend`（OpenAI 兼容，SSE 流式，真实模型调用）
- `BackendChunk`（streaming turn chunk type: text_delta / stop_reason）
- `BackendTurnResult` 新增 `total_cost_usd` 字段用于真实 cost 跟踪

### turn 执行层

`engine.py` 提供：

- `PreparedTurn`
- `QueryTurnContext`
- `QueryTurnState`
- `BackendTurnExecutor`
- `PlaceholderTurnExecutor`
- `RuntimeTurnExecutor`
- `QueryRuntime`

### 关键方法

`QueryRuntime` 新增：
- `rewind_messages(count)` — 回退 N 条消息
- `record_file_mutation(path, operation)` — 记录文件变更
- `_run_stop_hooks(executed, session_id)` — 每轮模型响应后分发 stop hook
- `_check_budget_and_maybe_compact(executed, tool_outputs)` — 检查 cost/token budget
- `_check_auto_compact(tool_outputs)` — 根据 token 使用量自动触发 compact

### 包导出面

`__init__.py` 把 backend / engine 里的核心类型重新导出，方便上层直接引用。

## 关键依赖与配置

- 依赖 `py_claw.commands`、`py_claw.schemas.common`、`py_claw.schemas.control`、`py_claw.settings.loader`、`py_claw.tools.base`
- 该层不直接负责 CLI 参数解析，而是承接已准备好的 turn context
- backend.py 现已提供真实模型后端（`AnthropicQueryBackend` / `ApiQueryBackend`（OpenAI 兼容，SSE 流式）/ `SdkUrlQueryBackend`），`cli/main.py` 依据配置选择后端并接入完整工具循环；`PlaceholderQueryBackend` / `PlaceholderTurnExecutor` 仅作为未配置后端时的回退路径保留

## 数据模型

高价值结构包括：

- turn 的 prompt / schema / model / effort / tool 选择信息
- backend usage / model usage / cost 统计
- tool call 结果与 executed turn 结果

## 测试与质量

- 这是一个较新的运行时子域，建议和 `cli/`、`schemas/`、`tools/` 一起看
- 若继续深扫，应优先确认 placeholder backend 与 runtime defaults 的边界

## 相关文件清单

- `__init__.py`
- `backend.py`
- `engine.py`
- `stop_hooks.py`

## 变更记录 (Changelog)

- 2026-06-21：新增 `stop_hooks.py`；engine.py 新增 rewind/stop_hook/budget/compact 方法；backend.py 新增 BackendChunk 和 total_cost_usd 真实 cost 跟踪
- 2026-04-11：新增 query 运行时导航文档。
