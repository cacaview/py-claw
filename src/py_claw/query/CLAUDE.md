[根目录](../../../CLAUDE.md) > [src](../CLAUDE.md) > **py_claw/query**

# py_claw/query

## 模块职责

`py_claw/query/` 是 Python 主实现中的 query runtime 层，负责把上层控制循环准备好的 turn 组织成可执行结构，并通过 backend / executor 抽象完成一次查询轮次。它是当前运行时中“模型推理/占位后端”与 CLI 控制循环之间的桥接层。

## 入口与启动

- 后端适配：`backend.py`
- turn 编排：`engine.py`
- 包导出：`__init__.py`

## 对外接口

### 后端抽象

`backend.py` 提供：

- `QueryBackend`
- `BackendTurnResult`
- `BackendToolCall`
- `PlaceholderQueryBackend`
- `SdkUrlQueryBackend`

### turn 执行层

`engine.py` 提供：

- `PreparedTurn`
- `QueryTurnContext`
- `QueryTurnState`
- `BackendTurnExecutor`
- `PlaceholderTurnExecutor`
- `RuntimeTurnExecutor`
- `QueryRuntime`

### 包导出面

`__init__.py` 把 backend / engine 里的核心类型重新导出，方便上层直接引用。

## 关键依赖与配置

- 依赖 `py_claw.commands`、`py_claw.schemas.common`、`py_claw.schemas.control`、`py_claw.settings.loader`、`py_claw.tools.base`
- 该层不直接负责 CLI 参数解析，而是承接已准备好的 turn context
- 当前包含 placeholder backend / executor 路径，适合作为未来真实模型接入的接缝

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

## 变更记录 (Changelog)

- 2026-04-11：新增 query 运行时导航文档。
