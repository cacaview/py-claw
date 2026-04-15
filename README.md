# py-claw

**Python 版 Claude Code 运行时**，兼容 Claude Code SDK 与 CLI 协议。

## 定位

`py-claw` 是一个本地运行时，实现了对上游 Claude Code 控制协议、结构化 I/O、权限判定、设置加载、内置工具、hook 运行时、MCP 状态建模和 query runtime 的兼容覆盖。

- **主运行时**：`src/py_claw/` — Python 实现
- **上游参考**：`ClaudeCode-main/` — TypeScript 还原参考树

## 核心能力

| 子系统 | 覆盖范围 |
|--------|---------|
| **CLI** | `stream-json` 控制循环、Structured I/O、SSE/WebSocket transport |
| **协议** | Pydantic 控制请求/响应 envelope、SDK message 联合类型 |
| **设置** | 多源加载与合并（user/project/local/flag/policy） |
| **权限** | allow/ask/deny 规则引擎、glob 模式匹配、MCP 规则 |
| **工具** | 46+ 内置工具（Read/Edit/Write/Bash/LSP/Task*/Agent 等）本地执行 |
| **Hook** | 27 个 hook 事件、输入改写、放行/拒绝、失败回调 |
| **MCP** | 动态 server 状态快照、stdio/SSE/WebSocket transport |
| **Query** | turn 编排、后端适配、流式响应 |
| **Insights** | 多阶段会话分析管道（scan/extract/dedup/aggregate/narrative） |

## 安装

```bash
pip install -e .
```

## 运行

```bash
# CLI 入口
py-claw --version

# 结构化控制模式
py-claw --input-format stream-json --output-format stream-json
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 查看版本
python -m py_claw.cli.main --version
```

## 项目结构

```
py-claw/
├── src/py_claw/           # Python 主实现
│   ├── cli/               # CLI 入口、控制循环、Structured I/O
│   ├── query/             # Query 编排与后端适配
│   ├── schemas/           # Pydantic 协议模型
│   ├── settings/          # 多源设置加载
│   ├── permissions/        # 权限规则引擎
│   ├── tools/             # 内置工具（46+）
│   ├── hooks/             # Hook schema 与运行时
│   ├── mcp/               # MCP server 状态建模
│   ├── services/          # 运行时服务层
│   └── ui/                # Textual 终端 UI
├── tests/                 # pytest 测试（1700+ 测试）
└── ClaudeCode-main/      # TypeScript 上游参考
```

## 测试覆盖

1700+ 测试覆盖：CLI 参数、stream-json、settings 合并、权限规则、工具执行、hook 生命周期、MCP 状态、Insights 分析管道、Remote Session、Agent 等。

## 技术栈

- Python ≥ 3.12
- Pydantic ≥ 2.8（协议模型）
- Textual ≥ 0.50（终端 UI）
- pytest ≥ 8（测试）
- anthropic ≥ 0.18（模型 API）

## 文档

- [CLAUDE.md](CLAUDE.md) — 项目架构与模块索引
- [todo.md](todo.md) — 上游对齐状态与 TODO
- [src/py_claw/CLAUDE.md](src/py_claw/CLAUDE.md) — Python 运行时详细文档
- [ClaudeCode-main/CLAUDE.md](ClaudeCode-main/CLAUDE.md) — TypeScript 参考树导航
