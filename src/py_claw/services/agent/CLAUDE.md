[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **services/agent**

# services/agent

## 模块职责

`services/agent/` 是 AgentTool Phase 4 的高级服务模块，为 forked agent 提供：

- **transcript.py** — 会话 transcript 录制与持久化
- **tracing.py** — Perfetto 层级追踪
- **hooks.py** — Frontmatter hook 注册与执行
- **skill_preload.py** — Skill 预加载
- **remote_backend.py** — Remote/tmux 后端

## 入口与启动

- 模块导出：`services/agent/__init__.py`
- 主服务类：`AgentTranscriptService`、`PerfettoTracingService`、`AgentHooksService`、`SkillPreloadService`、`RemoteAgentBackend`

## 对外接口

### Transcript Service

- `record_sidechain_transcript()` — 追加消息到 transcript JSONL 文件
- `write_agent_metadata()` — 写入 agent 元数据 (agentType/worktreePath/description)
- `set_agent_transcript_subdir()` / `clear_agent_transcript_subdir()` — 子目录路由
- `AgentTranscriptService` — 服务封装

### Tracing Service

- `PerfettoTracingService.is_enabled()` — 检查追踪是否启用
- `PerfettoTracingService.register_agent()` — 注册 agent 到追踪层级
- `PerfettoTracingService.unregister_agent()` — 取消注册
- 环境变量：`PY_CLAW_PERFETTO_TRACING=1` 启用

### Hooks Service

- `register_frontmatter_hooks()` — 注册 agent 生命周期内有效的 hook
- `clear_session_hooks()` — 清理 agent 的 hook
- `execute_subagent_start_hooks()` — 执行 SubagentStart hooks 并 yield 额外上下文
- `AgentHooksService` — 服务封装

### Skill Preload Service

- `resolve_skill_name()` — 解析 skill 名称（支持 plugin 前缀和 suffix 匹配）
- `preload_skills()` — 预加载 skill 并返回格式化的 user messages
- `SkillPreloadService` — 服务封装

### Remote Backend

- `RemoteAgentBackend` — 远程 agent 后端基类
- `TmuxAgentBackend` — tmux 会话执行后端
- `SSHAgentBackend` — SSH 远程执行后端
- `create_remote_backend()` — 后端工厂函数

## 关键依赖与配置

- Transcript 使用 `~/.claude/sessions/<session_id>/subagents/<agent_id>/` 路径约定
- Tracing 输出到 `~/.claude/traces/<agent_id>.json`
- Remote backend 支持 `backend_type: "tmux"` 或 `"ssh"`

## 数据模型

- `AgentMetadata` — agent 元数据
- `AgentHook` — frontmatter hook 定义
- `TraceSpan` — Perfetto 追踪 span
- `PreloadedSkill` — 预加载 skill
- `SkillPreloadResult` — 预加载结果
- `RemoteBackendConfig` — 远程后端配置

## 测试与质量

- `tests/test_agent_transcript.py` — 19 个测试
- `tests/test_agent_tracing.py` — 16 个测试
- `tests/test_agent_hooks.py` — 14 个测试
- `tests/test_agent_skill_preload.py` — 21 个测试
- `tests/test_agent_remote_backend.py` — 16 个测试
- **总计 107 个 Phase 4 测试，全部通过**

## 变更记录 (Changelog)

- 2026-04-13：实现 Phase 4 全部 5 个服务 + 107 个测试
