[根目录](../../CLAUDE.md) > [src](../CLAUDE.md) > **py_claw**

# py_claw

## 模块职责

`py_claw` 是 Python 版 Claude Code 运行时的主体实现，当前核心子系统包括：

- CLI 与控制循环（`cli/`）
- 结构化输入输出 + SSE/WebSocket transport（`cli/structured_io.py`）
- settings 加载与校验（`settings/`）
- 权限规则建模与求值（`permissions/`）
- 内置工具执行运行时（`tools/`，46+ 个工具）
- MCP 状态快照建模（`mcp/`）
- hook schema 与命令 hook 运行时（`hooks/`）
- 任务列表与后台 shell 任务运行时（`tasks.py`）
- 命令定义与执行（`commands.py`）
- 插件系统（`plugins/`， builtin/plugin 注册）
- 命令运行时（`command_runtime.py`，lazy-loading、feature gates）
- Skill 发现与执行（`skills.py`）
- Query runtime 与后端适配（`query/`）
- 运行时服务（`services/`）
- SSH 会话管理（`ssh/`）
- Buddy companion 系统（`buddy/`，deterministic roll、ASCII sprite、prompt 集成）

## 入口与启动

- CLI 入口：`cli/main.py`
- 关键请求分发：`cli/control.py`
- 运行态：`cli/runtime.py`

## 对外接口

- `schemas/control.py`：控制请求/响应 envelope、initialize、get_settings、mcp_status 等
- `schemas/common.py`：权限结果、Hook 输入/输出、MCP server 模型、SDK message 联合类型、AgentDefinition、SlashCommand 等
- `tools/runtime.py`：内置工具执行主链路
- `tools/discover_skills_tool.py`：技能发现工具 (DiscoverSkills, GetSkillDetails)
- `tasks.py`：任务记录、后台 Bash 进程跟踪、日志输出与 stop/wait 语义
- `hooks/runtime.py`：命令 hook 调度与权限决策回写（27 个 hook events）
- `mcp/runtime.py`：MCP server 状态折叠与快照生成、tools/list、tools/call、prompts 方法
- `services/compact/`：上下文压缩（snip/reactive/auto_trigger/micro_compact）
- `services/session_memory/`：会话记忆提取与状态管理
- `services/oauth/`：OAuth 2.0 授权码流程
- `services/lsp/`：LSP server 管理与 diagnostics
- `services/api/`：API 类型与客户端
- `ui/`：Textual 终端 UI 层（Textual 重写 Ink/React 组件，Phase 1-4 完成）
- `ssh/`：SSH 会话管理（SSHSessionManager、create_ssh_session）
- `buddy/`：Companion 系统（roll_companion、render_sprite、get_companion_intro_attachment）
- `commands.py`：90+ 个 slash commands 实现（含 install-github-app、remote-env、sandbox-toggle 等）
- `commands/init_verifiers.py`：`/init-verifiers` 命令实现
- `cli/main.py`：`main()` 作为包脚本入口
- `config/`：统一配置加载（`~/.config/py-claw/config.json`，XDG Base Directory 规范）
- `__init__.py`：当前仅暴露 `__version__`，不是稳定顶层 API 聚合层

## 关键依赖与配置

- 根配置：`../../pyproject.toml`
- 外部依赖：`pydantic>=2.8`
- 运行时设置来源：用户/项目/本地/flag/policy 五层叠加
- 轻状态对象广泛采用 `@dataclass(slots=True)`

## 数据模型

此模块没有数据库；核心模型包括：

- `SettingsModel` 及权限/settings 相关结构
- `PermissionRuleValue`、`PermissionResultAllow`、`PermissionResultDeny`
- `SDKControlRequest` / `SDKControlResponseEnvelope`
- `ToolExecutionResult`
- `TaskRecord`
- `HookDispatchResult`
- `McpServerStatusModel`
- `CompactionResult`、`SessionMemoryConfig`、`OAuthTokens` 等

## 测试与质量

- 566 个测试覆盖 CLI、schema、permission、settings、tools、hooks、MCP、compact、session_memory、oauth、lsp、agent 等
- 类型标注完整、dataclass + Pydantic 分层清晰
- 测试覆盖核心规则语义、后台任务生命周期、hook 输出处理
- Agent Phase 4 新增 107 个测试（transcript/tracing/hooks/skill_preload/remote_backend）

## 常见问题 (FAQ)

### 为什么很多字段是 camelCase？
因为要尽量贴近上游 Claude Code SDK/协议字段形状。

### `py_claw` 顶层包现在暴露稳定 Python API 吗？
还没有。当前 `__init__.py` 只公开 `__version__`，项目主要使用方式仍是 CLI/运行时，而不是顶层 import API。

### 这里是否已经实现完整工具执行？
已实现 46+ 个内置工具，包括 Read/Edit/Write/Glob/Grep/Bash/PowerShell/Task*/LSP/Skill/Agent/McpAuth/Tungsten/OverflowTest/Monitor 等，但仍是轻量运行时。

### MCP 是否已经能真实连外部 server？
`mcp/runtime.py` 已实现 stdio、SSE、WebSocket transport，支持 `list_tools()`、`call_tool()`、`list_prompts()` 等方法。SDK/claudeai-proxy transport 待实现。

## 相关文件清单

- `__init__.py`
- `cli/main.py`
- `cli/control.py`
- `cli/structured_io.py`
- `cli/runtime.py`
- `tasks.py`
- `commands.py`
- `commands/init_verifiers.py`
- `skills.py`
- `plugins/__init__.py`
- `plugins/types.py`
- `plugins/builtin.py`
- `plugins/manifest.py`
- `plugins/registry.py`
- `plugins/CLAUDE.md`
- `command_runtime.py`
- `tools/runtime.py`
- `tools/registry.py`
- `tools/local_fs.py`
- `tools/local_shell.py`
- `tools/powershell.py`
- `tools/lsp_tool.py`
- `tools/agent_tools.py`
- `tools/skill_tool.py`
- `tools/discover_skills_tool.py`
- `hooks/runtime.py`
- `mcp/runtime.py`
- `schemas/control.py`
- `schemas/common.py`
- `settings/loader.py`
- `permissions/engine.py`
- `query/backend.py`
- `query/engine.py`
- `services/compact/`
- `services/session_memory/`
- `services/oauth/`
- `services/lsp/`
- `services/api/`
- `services/agent/`
- `services/context/`
- `services/config/`
- `services/install_github_app/` — GitHub Actions 集成（使用 gh CLI 与 GitHub API）
- `utils/cron.py`
- `utils/attachments.py`
- `utils/extra_usage.py`
- `utils/fast_mode.py`
- `utils/background_housekeeping.py`
- `utils/exec_file_no_throw.py`
- `utils/early_input.py`
- `utils/embedded_tools.py`
- `utils/auth_portable.py`
- `utils/auth_file_descriptor.py`
- `ui/textual_app.py`
- `ssh/__init__.py`
- `ssh/session.py`
- `buddy/__init__.py`
- `buddy/types.py`
- `buddy/companion.py`
- `buddy/sprites.py`
- `buddy/prompt.py`

## 变更记录 (Changelog)

- 2026-04-15：深化 `/insights` 多阶段分析管道（Phase A-H），切换至 `session_storage/` 数据源；新增 `SessionMeta`、`SessionFacet`、`MultiClaudingStats`、`NarrativeSections`、`AggregatedInsightsData` 等 pipeline 类型；实现 `scan_session_logs`、`extract_session_meta`、`deduplicate_session_branches`、`aggregate_insights_data`、`detect_multi_clauding`、`format_insights_report` 等函数；`/insights` handler 已重新接线至 service；新增 `tests/test_services_insights.py`（21 个测试全部通过）
- 2026-04-15：继续深化 `/install` 命令，接入 `services/native_installer/` 与 config service；现支持真实安装状态查看、stable/latest 安装流程、pinned version 偏好记录与 update channel 持久化，并新增命令测试。
- 2026-04-15：补齐 `services/bridge/poll_config.py` 的动态配置接入，bridge poll config 现已通过 analytics dynamic config 读取 `tengu_bridge_poll_interval_config`；新增对应测试，关闭此前唯一保留的明确 runtime 缺口。
- 2026-04-15：继续深化轻量命令实现，新增 `/remote-setup`（remote managed settings 状态/清缓存）、`/debug-tool-call`（diagnostic tracking 摘要）与 `/issue`（gh CLI 只读 issue list/show）；最新递归复扫确认 Python 侧仅剩 `services/bridge/poll_config.py` 未接入真实 GrowthBook 刷新值这一项明确 runtime 缺口。
- 2026-04-14：新增 `install-github-app` 命令和 `services/install_github_app/` 模块，实现 GitHub Actions 集成（使用 gh CLI 与 GitHub API 创建 workflow 和 PR）
- 2026-04-14：新增 `ssh/` 模块（SSH 会话管理）和 `buddy/` 模块（Companion sprite 系统、deterministic roll、ASCII 渲染、prompt 集成）
- 2026-04-14：新增 plugins/、command_runtime.py、utils/attachments.py，新增 DiscoverSkillsTool, GetSkillDetailsTool, init-verifiers 命令，services/context/, services/config/, utils/cron.py 等 Utils 已完成
- 2026-04-13：补全文档，纳入 services/agent/ 模块（Phase 4: transcript/tracing/hooks/skill_preload/remote_backend）
- 2026-04-12：补全文档，纳入 services/、commands.py、query/、LSP tool 等新增子系统。
- 2026-04-08：补全文档，纳入 tools/hooks 真实运行时与 MCP 状态建模细节。