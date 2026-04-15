[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **services**

# services

## 模块职责

`services/` 包含运行时服务层，负责模型无关的横切能力：

- API 类型与客户端（`api/`）
- 上下文压缩（`compact/`）
- 会话记忆（`session_memory/`）
- 会话持久化存储（`session_storage/`）
- OAuth 2.0 授权（`oauth/`）
- LSP server 管理与 diagnostics（`lsp/`）
- Agent 服务（`agent/`）— Forked agent 高级服务
- Chrome 扩展集成（`chrome/`）— Claude in Chrome 浏览器扩展支持
- IDE 集成（`ide/`）— IDE 检测、lockfile 管理、扩展安装状态
- Context 上下文（`context/`）— 系统/用户上下文注入、Git 状态、CLAUDE.md 加载
- Doctor 诊断（`doctor/`）— 系统诊断、安装检查、上下文警告
- Commit 服务（`commit/`）— Git commit 分析、attribution 跟踪、commit prompt 生成
- Diff 服务（`diff/`）— 结构化 diff 生成、LCS 算法、hunk 格式

## 子模块导航

- `auth/` — 认证工具函数（OAuth token、API key、订阅状态、云厂商凭证）（U1）
- `api/CLAUDE.md` — API 类型、流式解析、错误处理（U2）
- `log/` — 日志工具（debug 模式、错误日志）（U3）
- `debug/` — debug 模块重导出（U4）
- `stats/` — 统计聚合（streaks、daily activity、session stats）（U5）
- `bash/` — Shell 工具（shell_quote、shell_completion）（U6）
- `session_state/` — Session 状态工具（U7）
- `cron/` — 定时任务（cron 解析、next run 计算）（U8）
- `cleanup/` — 清理工具（messages/sessions/plans/debug logs）（U9）
- `suggestions/` — 建议模块（command/shell_history/directory）（U10）
- `chrome/` — Chrome 扩展检测、浏览器检测、URL 打开
- `install_github_app/` — GitHub Actions 集成（使用 gh CLI 与 GitHub API 创建 workflow 和 PR）
- `context/CLAUDE.md` — Git 状态、CLAUDE.md 加载、系统/用户上下文
- `compact/CLAUDE.md` — 上下文压缩、snip/reactive/micro_compact
- `session_memory/CLAUDE.md` — 会话记忆提取、状态管理
- `session_storage/` — 会话文件 I/O、路径管理、搜索
- `oauth/CLAUDE.md` — OAuth 授权码流程、PKCE、token refresh
- `lsp/CLAUDE.md` — LSP server 管理、diagnostics、工具接口
- `agent/CLAUDE.md` — Agent transcript/tracing/hooks/skill_preload/remote_backend
- `config/CLAUDE.md` — 全局/项目配置、Auth 防丢失保护、备份恢复
- `ide/CLAUDE.md` — IDE 检测、lockfile 管理、连接功能
- `skills/CLAUDE.md` — 统一 skill 管理门面，协调 discovery/manager/search
- `doctor/CLAUDE.md` — 系统诊断、安装检查、上下文警告
- `commit/CLAUDE.md` — Git commit 分析、attribution 跟踪、commit prompt 生成
- `diff/CLAUDE.md` — 结构化 diff、LCS 算法、hunk 格式化
- `mcp_auth/` — MCP OAuth 鉴权、XAA、VSCode SDK 集成、channel 权限、elicitation 处理
- `bridge/` — Bridge 远程控制服务（S7-S23 补充模块：peer_sessions、poll_config、flush_gate、capacity_wake、debug_utils、work_secret、session_id_compat、bridge_pointer、bridge_status_util、repl_bridge_handle、repl_bridge_transport、inbound_messages、inbound_attachments、env_less_bridge_config）
- `remote/` — CCR 远程会话管理（RemoteSessionManager、SessionsWebSocket、message_adapter、permission_bridge）
- `worktree/` — Agent worktree 管理（createAgentWorktree/removeAgentWorktree/cleanupStaleAgentWorktrees）
- `model/` — 模型选择、别名解析、API provider 检测（U11）
- `permissions/` — Auto mode 状态、分类器决策、路径验证（U12）
- `telemetry/` — OpenTelemetry 事件日志（U13）
- `sandbox/` — 沙箱适配器、配置转换（U15）
- `secure_storage/` — 平台安全存储（Keychain/明文）（U16）
- `deep_link/` — Deep link URI 解析和协议注册（U17）
- `desktop_deep_link.py` — Claude Desktop 安装状态检测和会话交接
- `file_persistence/` — BYOC 模式文件持久化（U18）
- `native_installer/` — 原生安装器、版本管理（U19）
- `powershell/` — PowerShell AST 解析、危险 cmdlet（U20）

## 变更记录 (Changelog)

- 2026-04-15：深化 `insights/` 管道，实现 Phase A-H 完整多阶段分析链（session scan、meta 提取、branch dedup、facet cache、aggregate、multi-clauding detection、narrative generation stub），数据源切换至 `session_storage/`；新增 `tests/test_services_insights.py`（21 个测试全部通过）
- 2026-04-15：新增 `worktree/` 模块，实现 Agent worktree 管理（createAgentWorktree/removeAgentWorktree/cleanupStaleAgentWorktrees），包含 ephemeral slug 模式匹配和 stale worktree 清理功能
- 2026-04-14：新增 `install_github_app/` 模块，实现 GitHub Actions 集成（使用 gh CLI 与 GitHub API 创建 workflow 和 PR）
- 2026-04-14：新增 `remote/` 模块，实现 CCR 远程会话管理（RemoteSessionManager、SessionsWebSocket、message_adapter、permission_bridge），P0 核心功能缺口已补充
- 2026-04-14：新增 `desktop_deep_link.py`，实现 Claude Desktop 安装状态检测和会话交接
- 2026-04-14：新增 auth/、api/、log/、debug/、stats/、bash/、session_state/、cron/、cleanup/、suggestions/ 模块，完成 U1-U10 功能
- 2026-04-14：新增 model/、permissions/、telemetry/、sandbox/、secure_storage/、deep_link/、file_persistence/、native_installer/、powershell/ 模块，完成 U11-U20 功能
- 2026-04-14：新增 Bridge S7-S23 补充模块（peer_sessions、poll_config、flush_gate、capacity_wake、debug_utils、work_secret、session_id_compat、bridge_pointer、bridge_status_util、repl_bridge_handle、repl_bridge_transport、inbound_messages、inbound_attachments、env_less_bridge_config）。Bridge 34/34 文件全部完成！
- 2026-04-13：新增 `diff/` 模块，实现 M9 功能（结构化 diff、LCS 算法、hunk 格式化）
- 2026-04-13：新增 `commit/` 模块，实现 M10 功能（Git commit 分析、attribution 跟踪、commit prompt 生成）
- 2026-04-13：新增 `doctor/` 模块，实现 M8 功能（系统诊断、安装检查、上下文警告）
- 2026-04-13：新增 `/session` 命令模块（`py_claw/session.py`），实现 M6 功能（远程会话 URL + QR 码显示）
- 2026-04-13：新增 `skills/` 模块，实现 M7 功能（统一 skill 管理门面，协调 discovery/manager/search）
- 2026-04-13：新增 `context/` 模块，实现 M4 功能（Git 状态、CLAUDE.md 加载、系统/用户上下文注入）
- 2026-04-13：新增 `ide/` 模块，实现 M5 功能（IDE 检测、lockfile 管理、连接功能）
- 2026-04-13：新增 `config/` 模块，实现 M3 功能（全局/项目配置、Auth 防丢失保护、备份恢复）
- 2026-04-13：新增 `session_storage/` 模块，实现会话持久化和检索功能
- 2026-04-13：新增 `chrome/` 模块，实现 Chrome 扩展集成服务
- 2026-04-12：补全 services 子模块文档。