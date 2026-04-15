[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **tools**

# tools

## 模块职责

`tools/` 已经包含真实内置工具执行链，而不只是权限目标映射。它负责：

- 维护内置工具注册表（含 REPL 模式过滤）
- 用 Pydantic 校验工具输入
- 在执行前后接入 Hook 运行时
- 把工具输入转换为权限引擎可判定的目标
- 执行本地文件与 shell 工具

## 入口与启动

- 运行时入口：`runtime.py::ToolRuntime.execute`
- 注册表构建：`registry.py::build_default_tool_registry`
- REPL 模式检测：`registry.py::is_repl_mode_enabled`
- 本地文件工具：`local_fs.py`
- Shell 工具：`local_shell.py`（Bash）、`powershell.py`（PowerShell）
- LSP 工具：`lsp_tool.py`
- 协议/抽象：`base.py`

## 对外接口

默认内置工具（32 个）：

| 工具 | 文件 | 说明 |
|---|---|---|
| `Read` | `local_fs.py` | 文件读取 |
| `Edit` | `local_fs.py` | 文件编辑 |
| `Write` | `local_fs.py` | 文件写入 |
| `NotebookEdit` | `local_fs.py` | Jupyter notebook 编辑 |
| `Glob` | `local_fs.py` | 文件模式匹配 |
| `Grep` | `local_fs.py` | 内容搜索（30+ 文件类型） |
| `Bash` | `local_shell.py` | Bash 命令执行 |
| `PowerShell` | `powershell.py` | PowerShell 命令执行 |
| `Agent` | `agent_tools.py` | Agent 执行（worktree 隔离） |
| `SendMessage` | `agent_tools.py` | 向 agent/teammate 发消息 |
| `AskUserQuestion` | `ask_user_question_tool.py` | 向用户提问 |
| `EnterPlanMode` | `plan_mode_tools.py` | 进入计划模式 |
| `ExitPlanMode` | `plan_mode_tools.py` | 退出计划模式 |
| `EnterWorktree` | `worktree_tools.py` | 进入 git worktree |
| `ExitWorktree` | `worktree_tools.py` | 退出 git worktree |
| `TaskCreate` | `task_tools.py` | 创建任务 |
| `TaskGet` | `task_tools.py` | 获取任务 |
| `TaskList` | `task_tools.py` | 列出任务 |
| `TaskUpdate` | `task_tools.py` | 更新任务 |
| `TaskOutput` | `task_tools.py` | 获取任务输出 |
| `TaskStop` | `task_tools.py` | 停止任务 |
| `LSP` | `lsp_tool.py` | LSP 操作（定义/引用/hover 等 8 种操作） |
| `ListMcpResources` | `mcp_resource_tools.py` | 列出 MCP 资源 |
| `ReadMcpResource` | `mcp_resource_tools.py` | 读取 MCP 资源 |
| `Skill` | `skill_tool.py` | Skill 执行（inline/fork） |
| `DiscoverSkills` | `discover_skills_tool.py` | 技能发现 |
| `GetSkillDetails` | `discover_skills_tool.py` | 获取技能详情 |
| `WebFetch` | `web_fetch_tool.py` | Web 内容抓取 |
| `WebSearch` | `web_search_tool.py` | Web 搜索 |
| `Config` | `config_tool.py` | 配置操作 |
| `ConfigSet` | `config_tool.py` | 设置配置项 |
| `ConfigList` | `config_tool.py` | 列出配置项 |

REPL 模式下以下工具被过滤（通过 REPL 批量操作）：

- `Read`, `Write`, `Edit`, `Glob`, `Grep`, `Bash`, `NotebookEdit`, `Agent`

运行时主流程：

1. `ToolRuntime` 校验输入模型
2. 计算 permission target
3. 触发 `PreToolUse`
4. 调用 `PermissionEngine`
5. 执行 tool
6. 成功时触发 `PostToolUse`
7. 失败时触发 `PostToolUseFailure`

## 关键依赖与配置

- 用 Pydantic BaseModel 表达工具输入模型
- 依赖 `HookRuntime` 接入 hook 生命周期
- 依赖 `PermissionEngine` 做 allow/deny 判定
- 未注册工具由 `ToolRegistry.require()` 抛 `KeyError`
- REPL 模式由 `CLAUDE_CODE_REPL` / `CLAUDE_REPL_MODE` 环境变量控制

## 数据模型

- `ToolDefinition`
- `ToolPermissionTarget`
- `ToolRuntimePermissionTarget`
- `ToolExecutionResult`
- `ToolRegistry`

## 测试与质量

- `tests/test_tools_runtime.py` 已直接覆盖内置工具注册、`Read`、`Write`、`Edit`、`Glob`、`Grep`、`Bash`、`TaskOutput`、`TaskStop` 与权限拒绝路径
- Hook 交互在 `tests/test_hooks_runtime.py` 中补充覆盖了输入改写与失败后 hook 回调
- `tests/test_lsp_runtime.py` 覆盖 LSP diagnostics registry、server manager、config loading
- 该层现在属于"真实执行 + 轻量编排"，不是纯 schema 层

## 常见问题 (FAQ)

### 这里会真正执行 Read/Bash 吗？
会。`local_fs.py` 提供 `Read/Edit/Write/Glob/Grep` 的本地实现，`local_shell.py` 提供 `Bash` 的本地执行实现；其中 `run_in_background=true` 会通过 `TaskRuntime` 创建后台任务并把输出写到工作目录下的 `.py_claw/tasks/*.log`。

### PowerShell 和 Bash 是什么关系？
`BashTool` 使用 `bash.exe`（WSL/Git Bash）执行命令，`PowerShellTool` 使用 `pwsh`（7+）或 `powershell`（5.1）。两个工具相互独立，各自有安全检查。

### BashTool AST 和安全检查是什么？
`tools/bash/` 子模块提供 Bash 命令的抽象语法树解析和安全检查：
- `ast.py` — AST 节点定义、命令分类、单词提取、重定向解析
- `parser.py` — Bash 解析器（50ms 超时保护，防止解析死循环）
- `security.py` — 安全检查（critical/high/medium/low 四级告警，检测危险命令）

### REPL 模式是什么？
REPL 模式默认开启（interactive CLI），此时 `Read/Write/Edit/Glob/Grep/Bash/NotebookEdit/Agent` 工具对模型不可见，模型需通过 REPL 做批量操作。可通过 `CLAUDE_CODE_REPL=0` 禁用。

### 当前有哪些已确认限制？
- `Read.pages` 目前直接报错，PDF 分页尚未实现
- `Grep` 是 Python 正则搜索，不是 ripgrep 兼容实现
- `Grep.type` 字段当前会通过 schema 接受，但执行路径并未真正按文件类型过滤
- `Bash.dangerouslyDisableSandbox` 字段当前会通过 schema 接受，但本实现未实际接入 sandbox
- `LSP` 工具依赖 LSP server 配置，未配置时返回错误

## 相关文件清单

- `runtime.py`
- `registry.py`
- `local_fs.py`
- `local_shell.py`
- `powershell.py`
- `lsp_tool.py`
- `agent_tools.py`
- `ask_user_question_tool.py`
- `plan_mode_tools.py`
- `worktree_tools.py`
- `task_tools.py`
- `mcp_resource_tools.py`
- `skill_tool.py`
- `web_fetch_tool.py`
- `web_search_tool.py`
- `config_tool.py`
- `base.py`
- `__init__.py`

## 变更记录 (Changelog)

- 2026-04-13：新增 BashTool AST FAQ 说明（tools/bash/ 子模块：ast.py、parser.py、security.py）
- 2026-04-12：更新工具清单，纳入 LSPTool、PowerShellTool、AgentTool teammate、SkillTool inline/fork 等新增工具。
- 2026-04-08：补全文档，修正"仅权限目标映射"的过时结论，确认内置工具真实执行路径。