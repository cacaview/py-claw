# TODO — py-claw 工作进度

> 更新日期：2026-04-21

---

## 2026-04-21 变更记录

### 已完成

- **SessionSpawner + BridgeCore 集成**：在 `BridgeCore._handle_work_item()` 中添加了 `_spawn_child_process()` 调用，当 CCR 发送 work item 时自动 spawn 子 CLI 进程
- **SSH Tunnel 实现**：使用 `asyncssh` 库实现 `SSHSessionManager.connect()`，支持真实的 SSH 连接和本地端口转发
- **pyproject.toml**：添加 `asyncssh>=2.14,<3` 依赖
- **ErrorLogSink 实现**：新增 `FileErrorLogSink` 类，实现文件日志记录 (`utils/log.py`)
- **commands.py stubs 修复**：
  - `/privacy-settings reset` 现在调用 config service 真实重置隐私设置
  - `/context clear` 现在调用 session_memory state 真实重置
  - `/add-dir` 现在调用 config service 添加目录到 allowed list
- **SSH Reverse Tunnel 实现**：新增 `SSHClient.connect_reverse()` 和 `SSHService.create_reverse_tunnel()`，支持 `-R` 反向端口转发
- **Vim Service TUI 集成**：新增 `_publish_vim_mode_to_tui()` 将 vim 模式变更发布到全局 TUI store；新增 `get_tui_vim_mode()`、`is_vim_active_in_tui()`、`get_vim_status_for_tui()` 等 TUI 状态辅助函数；`toggle_vim_mode()` 和 `set_vim_mode()` 现在会在状态变更时同步到 TUI
- **YOLO 分类器接入**：将 `py_claw/permissions/yolo_classifier.py` 的真实分类器接入 `PermissionEngine.evaluate()` 作为 fallback；`classify_yolo_action()` 现在调用真实分类器（allowlist/denylist/Bash/PowerShell 检查），fail-open 设计仅在高置信度 deny 时阻止
- **Voice TUI 集成**：新增 voice 状态到 `TUIState`（`voice_state`/`voice_error`/`voice_interim_transcript`/`voice_final_transcript`）；新增 `update_tui_voice_state()` / `update_tui_voice_transcript()` 辅助函数；新增 `services/voice/hold_to_talk.py` HoldToTalk 上下文管理器（sounddevice 音频采集）；新增 `ctrl+shift+v` voice-hold 快捷键
- **ResumeScreen 重设计**：`ui/screens/resume.py` 完全重写，支持键盘导航（↑↓ Enter Esc a）、异步会话加载（`search_sessions()`）、all projects 切换、分页加载；新增 `load_session_for_resume()` 到 session_storage；新增 `format_session_timestamp()` 工具函数

### 项目缺口扫描 (2026-04-21)

发现以下未完成/存根实现，按优先级排序：

#### 高优先级 (影响核心功能)

| 模块 | 缺口 | 状态 |
|------|------|------|
| `utils/log.py` | `ErrorLogSink` 所有方法 NotImplementedError | ✅ 已完成 (FileErrorLogSink) |
| `commands.py` | 多处 stub 实现 | ✅ 已完成 (privacy-settings/context/add-dir) |
| `services/ssh/service.py` | 反向隧道 (reverse tunnel) NotImplementedError | ✅ 已完成 (-R flag) |
| `services/policy_limits/` | 始终返回 True | ⚠️ 故意 stub (fail-open 行为，完整实现需 OAuth) |
| `services/assistant/` | `discover_assistant_sessions()` 返回空列表 | ⚠️ 故意 stub (需后端 API) |

#### 中优先级 (影响用户体验)

| 模块 | 缺口 | 状态 |
|------|------|------|
| `services/voice_stream_stt/service.py` | 多处 NotImplementedError | ✅ 已是完整实现（stub 是动态替换模式，由 `connect_voice_stream()` 在运行时替换） |
| `services/insights/service.py` | Phase H narrative generation stub | ✅ 已是完整实现（LLM 调用 + fallback 机制） |
| `services/vim/service.py` | 简化实现，缺 TUI 集成 | ✅ 已完成（TUI store 同步 + TUI 状态辅助函数） |

#### 低优先级 (可后续迭代)

| 模块 | 缺口 | 状态 |
|------|------|------|
| `services/permissions/classifier_decision.py` | YOLO 分类器 stub | ✅ 已完成（接入真实分类器到 PermissionEngine） |
| `services/voice/` | audio-capture-napi 待实现 | ✅ 已完成（HoldToTalk + sounddevice 纯 Python 实现） |
| `state/observable.py` | Observable NotImplementedError | ⚠️ 基类设计模式（子类实现） |
| `ResumeConversation.tsx` | TS React 组件难移植 | ✅ 已完成（Python/Textual 重实现） |

---

## TUI 对齐任务（按步骤拆分）

### 1. Prompt suggestion UX 收敛与对齐 ✅

1. ✅ 审计 `PromptInput` 与 `PromptFooter` 的建议展示职责，确定单一展示面
2. ✅ 删除重复建议渲染，只保留 PromptFooter 作为单一展示面
3. ✅ 统一建议列表的滚动窗口、选中态、分页策略与可见性规则
4. ✅ 统一 `↑↓ / PageUp / PageDown / Tab / Esc` 的行为一致性（PageUp 不再 wrap）
5. ✅ 对齐空输入 `/`、部分命令、mid-input slash、path、shell history 的展示策略
6. ✅ 处理窄终端和矮终端下的建议列表退化方案
7. ✅ 补充 Prompt suggestion 交互测试（`tests/test_typeahead.py`，42 个测试全部通过）

**Bug 修复**：

- 修复 `get_suggestions()` 缺少 `AGENT`、`CHANNEL` 类型处理
- 修复 `_get_channel_suggestions()` 和 `_get_agent_suggestions()` 对 bare `#`/`@` 的处理（`group(2)` 可能为 `None`）
- 修复 `detect_type()` 对 bare `#` 的检测（正则改为 `?` 可选）

### 2. REPL 主消息区升级为专用消息列表 ✅

1. ✅ 审计现有 `RichLog` 用法与仓内可复用的消息列表/虚拟列表组件
2. ✅ 确定 Python 侧主 REPL 消息区替换方案（复用现有组件或补一个专用适配层）
3. ✅ 将 `src/py_claw/ui/screens/repl.py` 从 `RichLog` 切换到结构化消息列表
4. ✅ 对齐用户/助手/系统/tool/progress 消息的样式与分组展示
5. ✅ 验证长会话下的滚动、自动定位、性能与可读性
6. ✅ 补充主消息区渲染与交互测试

### 3. 主 REPL overlay 覆盖面补齐 ✅

1. ✅ 对照 TS `REPL.tsx` 盘点已存在但未接线的 Python dialog / overlay
2. ✅ 区分必须接入主 REPL 的高优先级交互面与可后置项
3. ✅ 先补主流程相关 overlay：permission / hook prompt / MCP elicitation / exit flow
4. ✅ 补齐当前主 REPL 已接线 overlay 的自动化覆盖：help / history / quick-open / model picker / tasks
5. ✅ 为主 REPL overlay 补入口、关闭回路、互斥状态与选择结果回填验证
6. ✅ 新增 `tests/test_tui/test_overlays.py`（18 个测试通过），并补 `PromptDialog` / `PermissionDialog` 最小交互验证
7. 后续体验增强类 overlay：idle/cost/remote/IDE onboarding/LSP-plugin recommendation 等继续排在下一轮

### 4. 窄屏 / 矮屏布局策略优化 ✅

1. ✅ 盘点当前 `<80` 宽与 `<20` 高时被直接隐藏的 UI 元素
2. ✅ 重新设计窄屏降级顺序，优先压缩而不是直接隐藏关键状态信息
3. ✅ 保留最小可用的 mode / hint / suggestion / help 信息
4. ✅ 为短终端设计独立的 footer / prompt 紧凑布局
5. ✅ 手动验证 80 列以下、20 行以下的可用性与信息密度

**本轮实现**：

- `textual_app.py` 不再在 `<80` / `<20` 时直接隐藏 `#pi-mode-bar` 与 `#repl-footer`
- `REPLScreen` 新增 compact layout 分发，统一驱动 `PromptInput` / `PromptFooter`
- `PromptInput` 新增 `compact_mode`，在窄/矮屏下缩短 model/mode/hint 文案并压缩 padding
- `PromptFooter` 新增 `compact_mode` + suggestion viewport 降级：`full` / `narrow` / `short` / `tight`
- `tight` 模式下隐藏 help row 与 pills，但保留最小 suggestion/status 反馈
- 新增 responsive 回归覆盖，验证 `<80`、`<20` 与 `<80 && <20` 三种布局约束

### 5. 主交互快捷键面补齐 ✅

1. ✅ 对照 TS REPL 梳理真正影响主流程的全局快捷键与模式切换入口
2. ✅ 标记 Python 已具备、缺失、或仅部分对齐的键位
3. ✅ 优先补主流程键位：帮助、导航、模式切换、overlay 入口、消息区交互
4. ✅ 统一 help 文案、状态栏提示、实际绑定三者一致性
5. ✅ 补充快捷键回归测试或最小交互 smoke case

**本轮实现**：

- `services/keybindings/service.py` 新增统一 shortcut source：help menu、status line、footer hint 共用同一套高频键位文案
- `PromptInput` 新增 `Shift+Tab` mode cycle，按 `normal → plan → auto → bypass → normal` 循环，并通过消息同步 footer / TUI store
- `REPLScreen` 改为复用 centralized status/footer shortcut hints，避免 `BINDINGS`、help、提示面各自漂移
- Help surface 现明确展示 `shift+tab`、`ctrl+g/l/r/p/m/t`、`?`、`enter/esc/tab/↑↓/→` 等当前真实主流程键位
- 新增 TUI 回归覆盖：模式循环、status/footer hint 对齐、help shortcut surface 对齐

### 6. Speculation / pipelined suggestions 接入 ✅

1. ✅ 审计现有 `SpeculationState` schema 与 query runtime 接口
2. ✅ 明确 Python 侧 speculation 的最小可用接入点
3. ✅ 在 suggestion engine / prompt UI 中接入 speculation 状态展示
4. ✅ 定义 speculation 接受、取消、失效时的 UI 行为
5. ✅ 补充对应测试，避免与现有 suggestion 流冲突

**实现内容**：

- `app_state.py`：新增 `CompletionBoundary` dataclass，扩展 `SpeculationState` + `TUIState` 增加 speculation 字段
- `analytics/service.py`：注册 `tengu_speculation_enabled` feature gate（默认 False）
- `speculation/constants.py`：`WRITE_TOOLS`/`SAFE_READ_ONLY_TOOLS`/`READ_ONLY_COMMANDS` frozensets + `MAX_SPECULATION_TURNS`/`MAX_SPECULATION_MESSAGES`
- `speculation/overlay.py`：`OverlayManager`（copy-on-write 隔离、路径解析、文件合并）+ `get_overlay_base()`/`create_overlay()`/`remove_overlay()`
- `speculation/read_only_check.py`：`ReadOnlyCheckResult` + `check_read_only_constraints()` + `check_tool_in_speculation()` bash 只读约束检查
- `fork/protocol.py`：`ForkResultMessage` 增加 `turn_count`/`boundary`/`output_tokens`，新增 `ForkSpeculationStartMessage`
- `fork/process.py`：`ForkedAgentProcess` 增加 `start_speculation()` fire-and-forget 方法
- `fork/model_executor.py`：`run_speculation_turn()` 异步模型执行（调用 Anthropic API + speculation 约束检查）
- `fork/child_main.py`：speculation 模式处理（`speculation_start` 消息 + `_run_speculation_async()`）
- `speculation/service.py`：`SpeculationService` 全局单例（`start_speculation()`/`accept()`/`abort()`）+ daemon thread 后台轮询
- `speculation/analytics.py`：`log_speculation()` analytics 事件
- `speculation/__init__.py`：模块导出 + 全局单例 `get_speculation_service()`
- `tui_state.py`：新增 `update_tui_speculation()` helper + `TUIState`/`TUIStateSnapshot` speculation 字段
- `prompt_footer.py`：新增 `speculation_status`/`boundary`/`tool_count` reactive fields + `_pills_row()` speculation pill 展示
- `repl.py`：新增 `set_speculation_state()` 方法，同步到 footer + global store
- `textual_app.py`：新增 `_register_speculation_callback()` 将 SpeculationService 状态变更同步到 UI footer

**测试**：111 个 TUI 测试通过，1788 个全量测试通过（2 skipped）

## 运行时深度

### 7. MCP 真实连接补全 ✅

1. ✅ 核对当前已接通的 SSE / WebSocket IDE transport 路径
2. ✅ 梳理 SDK transport 缺失点与外部 `sdk_message_handler` 依赖边界
3. ✅ 完成 SDK transport 接入或明确降级路径
4. ✅ 验证 claudeai-proxy / SDK / IDE transport 三条链路行为一致性
5. ✅ 补充 MCP 真实连接回归测试

**实现内容**：

- `runtime.py`：`McpRuntime` 已实现 stdio（持久化 `_PersistentStdioMcpProcess`）、HTTP、SSE、WebSocket、SDK（`_SdkMcpTransport`）、Claude AI Proxy（`_ClaudeAIProxyMcpTransport`）六种 transport，每种均有对应 dispatch 方法
- `_StdioMcpProcess`：每次请求 spawn 新进程；`_PersistentStdioMcpProcess` 复用单个子进程
- `_WebSocketMcpTransport`：wsproto 实现，手写 HTTP upgrade 握手
- `_SseMcpTransport`：标准请求-响应 + 流式 SSE 事件解析（`stream_messages()`）
- `_SdkMcpTransport`：依赖外部 `sdk_message_handler` 注入（`NotImplementedError` 无 handler 时）
- `_ClaudeAIProxyMcpTransport`：HTTP/SSE proxy，`_proxy_id` 路由
- `set_sdk_message_handler()`：注入 SDK message bridge
- `initialize()`：完整 MCP 握手流程（`initialize` → `notifications/initialized`）
- `is_session_expired()` / `reconnect_if_expired()`：inactive session 检测与重连
- `reconnect_server()`：重置 live state 到 pending 状态
- `send_notification()` / `cancel_request()`：JSON-RPC notification 支持
- `list_prompts()` / `get_prompt()` / `list_resource_templates()`：完整 prompts 和 resource template 方法
- `send_message()` / `list_tools()` / `call_tool()`：完整工具链调用
- `test_mcp_runtime.py`：11 个测试覆盖 HTTP/SSE transport、SDK/claudeai-proxy message handler、initialize 握手、prompts 方法

**测试**：11 个 MCP 测试通过，1788 个全量测试通过

### 8. Hook 深度补全 ✅

1. ✅ 审计当前 `async: True` hook 实现与返回语义
2. ✅ 设计 `asyncRewake` 的 Python 对齐方案（已识别差异：`async_` 为 fire-and-forget daemon thread；`asyncRewake` 需 exit_code=2 检测 + queue wake 机制）
3. ✅ 实现唤醒链路、状态传播与错误处理
4. ✅ 补充 hook 异步行为测试

**实现内容**：

- `schemas.py`：`BashCommandHook` 支持 `async_`（alias `async`）、`asyncRewake`、`timeout` 字段；27 个 hook 事件全部定义输入/输出 schema
- `runtime.py`：
  - `HookRuntime` 实现 27 个 `run_*` 方法（PreToolUse/PostToolUse/PostToolUseFailure/PermissionRequest/PermissionDenied/Elicitation/ElicitationResult/WorktreeCreate/WorktreeRemove/CwdChanged/Notification/UserPromptSubmit/SessionStart/SessionEnd/Stop/StopFailure/SubagentStart/SubagentStop/PreCompact/PostCompact/TeammateIdle/TaskCreated/TaskCompleted/ConfigChange/InstructionsLoaded/FileChanged/Setup）
  - `async_=True` hook 在 daemon thread 中执行，fire-and-forget，立即返回 `exit_code=-1`
  - 完整的 structured output 解析（`_parse_structured_output`），支持 `continue`/`decision`/`updatedInput`/`permissionDecision`/`additionalContext`
  - matcher 过滤（tool name + content glob 匹配）、`if` 条件过滤
  - `bash`/`powershell` shell 选择
  - `HookDispatchResult` 含 `executions`/`continue_`/`stop_reason`/`updated_input`/`permission_decision`/`action`/`content`
- `test_hooks_runtime.py`：37 个测试覆盖 PermissionRequest/PreToolUse/PostToolUseFailure/Elicitation/WorktreeCreate/WorktreeRemove/CwdChanged 的 blocking/allow/deny/match 行为

**已知缺口**：`asyncRewake` 的 exit_code=2 → queue wake 机制已实现（`on_async_hook_complete` callback，调用方负责 queue wake）；`prompt`/`http`/`agent` hook 类型的执行器尚未实现

**测试**：37 个 hook 测试通过，1788 个全量测试通过

## 测试与可靠性

### 9. TUI 自动化测试 ✅

1. ✅ 建立 pytest + textual 测试基础设施
2. ✅ 为 PromptInput / PromptFooter / REPLScreen 增加核心交互测试
3. ✅ 覆盖 suggestion 导航、overlay 打开关闭、状态栏更新、焦点恢复
4. ✅ 补充窄屏/矮屏布局测试

**实现内容**：
- `tests/test_tui/`（68 个测试）：覆盖 PromptInput/PromptFooter/REPLScreen/overlays/suggestions/compact layout
- `tests/test_typeahead.py`（43 个测试）：SuggestionEngine/CommandItem/Suggestion types
- `tests/test_tui_textual.py`：基本 async mount/integration 测试
- 总计 111 个 TUI 相关测试全部通过

**已知缺口**：无重大缺口。TUI 自动化基础设施已完整建立。

### 10. CLI + TUI 集成测试 ✅

1. ✅ 设计 `--tui` 启动到 prompt 提交的最小集成用例
2. ✅ 覆盖流式 SSE 响应解析（SSE 格式解析与多 delta 拼装）
3. ✅ 覆盖 overlay 交互与返回主 REPL
4. ✅ 覆盖异常路径、取消路径与关闭流程

**实现内容**：
- `tests/test_cli_tui.py`（18 测试）：CLI 入口、overlay 打开/关闭、prompt 生命周期、compact layout、mutual exclusivity
- `tests/test_tui_smoke.py`（4 测试）：`PyClawApp` 真实挂载、prompt 提交输入、`?` 帮助、`Ctrl+R` 历史搜索
- `tests/test_tui_textual.py`：基本 async mount/integration 测试
- `tests/test_tui/test_overlays.py`（18 测试）：overlay open/close/exclusivity
- `tests/test_cli_and_schemas.py::TestApiQueryBackendStreaming`（9 测试）：SSE 解析——单/多 text_delta、message_stop stop_reason、非数据行过滤、畸形 JSON 跳过、非 text delta 类型忽略、空流处理
- `tests/test_streaming_integration.py`（15 测试）：流式管道端到端验证——mock backend → engine → SDKPartialAssistantMessage 累积；REPLScreen 增量渲染与状态管理；SSE 事件格式
- `tests/test_tui_subprocess.py`（6 测试）：子进程冒烟测试——模块导入、REPLScreen 实例化、流式 `_StreamingList` 端到端集成

**流式基础设施完成**：
- `query/engine.py`：`handle_user_message` 改为 generator（`_StreamingList` wrapper 支持索引和迭代）；`_execute_prepared_turn`、`_finalize_outputs`、`_build_assistant_outputs` 均改为 yield 而非返回 list；`_execute_turn_with_outputs_streaming` 支持 executor 级别的流式
- `query/backend.py`：`BackendChunk` dataclass（`text_delta`/`stop_reason`）；`StreamingQueryBackend` Protocol；`ApiQueryBackend.run_turn_streaming()` 使用 `resp.iter_lines()` 逐行 yield `BackendChunk`；`_api_request_streaming` generator 函数
- `textual_app.py`：`_run_prompt` 增加对 `SDKPartialAssistantMessage` 的 `content_block_delta` 处理（`event.type == "content_block_delta"` → `_update_last_message(text, append=True)`）
- `_StreamingList`：lazy sequence wrapper，同时支持 streaming 迭代（`for output in handle_user_message()`）和测试索引访问（`outputs[2]`）

**Bug 修复**：`ListItem` 重名 ID 问题 — `_sanitize_item_id` 增加可选 `index` 参数

**新增测试**：
- `tests/test_streaming_integration.py`（18 测试）：完整流式管道验证——`MockStreamingExecutor` + `QueryRuntime` + `SDKPartialAssistantMessage` 累积；`BackendChunk` dataclass 行为；REPLScreen 增量消息渲染（`append_message`/`update_last_message`）；状态转换与 tool progress；TUI focus 管理；SSE 事件格式解析；新增 `TestPyClawAppStreamingFlow` 类（3 测试）覆盖完整 prompt → streaming → UI 更新流程、tool progress 处理、多 prompt 快速提交
- `tests/test_tui_subprocess.py`（6 测试）：子进程冒烟测试——TUI 模块导入、REPLScreen 实例化、`BackendChunk` 导入、流式 `_StreamingList` 端到端集成

**剩余缺口**（pytest 环境无法提供，需真实 TTY/ConPTY）：
- 端到端 `--tui` 启动后发送真实 prompt 并验证流式响应写入消息区（需要 `pexpect` 或 Windows ConPTY 工具）

**替代方案已完成**：
- `test_streaming_integration.py`（18 测试）：Mock 流式管道验证 — `MockStreamingExecutor` + `QueryRuntime` + `SDKPartialAssistantMessage` 累积，覆盖 `content_block_delta` / `message_stop` / `stream_request_start` 事件解析；新增 `TestPyClawAppStreamingFlow` 模拟完整 E2E 流式流程（prompt 提交 → QueryRuntime 处理 → UI 更新）
- `test_tui_subprocess.py`（6 测试）：子进程冒烟测试 — TUI 模块导入、REPLScreen 实例化、`BackendChunk` dataclass、流式 `_StreamingList` 端到端集成
- `test_cli_tui.py`（18 测试）：CLI+TUI 集成测试 — `--tui` flag 路由、overlay 键绑定、prompt 生命周期、compact layout、互斥性
- `test_tui_smoke.py`（4 测试）：PyClawApp 真实挂载、prompt 提交输入、`?` 帮助、`Ctrl+R` 历史搜索
- TUI 测试总计：121 个测试全部通过

**已知限制**：
- 真实 TTY 流式 E2E 测试（pexpect/ConPTY）在 pytest 环境中不可用
- WSL 中已完成测试环境配置（121 TUI 测试 + 54 MCP 测试全部通过），但真实的 TTY 交互仍需要交互式终端或 X11 桌面环境
- 手动验证清单：启动 `--tui`、输入 prompt、验证流式响应写入消息区、验证 Ctrl+C 中断

---

## Bridge/Remote 系统稳定性补齐

### 11. `/bridge start` 命令实现 ✅

1. ✅ 替换 stub 实现为真实命令处理器
2. ✅ 实现 `get_bridge_access_token()` / `get_bridge_base_url()` 配置访问函数
3. ✅ 实现环境注册 API 调用 `register_bridge_environment`
4. ✅ 添加 `CCR_BRIDGE_ENABLED` / `BRIDGE_BASE_URL` / `BRIDGE_MODE_ACCESS_TOKEN` 环境变量支持
5. ✅ 新增 `tests/test_bridge_service.py`（16 个测试全部通过）

**实现内容**：
- `/bridge status` - 显示 bridge 连接状态、凭证状态、环境信息
- `/bridge start` - 检查 entitlement → 尝试注册环境 → 报告结果
- `/bridge stop` - 当前返回 "not running"（待实现）

### 12. Bridge 轮询循环补全 ✅

1. ✅ 实现 `SessionApiClient.poll_for_work()` - GET `/v1/environments/{id}/work/poll`
2. ✅ 实现 `SessionApiClient.acknowledge_work()` - POST `/v1/environments/{id}/work/{workId}/ack`
3. ✅ 实现 `SessionApiClient.stop_work()` - POST `/v1/environments/{id}/work/{workId}/stop`
4. ✅ 实现 `BridgeCore._poll_messages()` - 真实轮询调用
5. ✅ 实现 `BridgeCore._register_environment()` - 环境注册
6. ✅ 实现 `BridgeCore._handle_work_item_async()` - 异步 work item 处理与确认
7. ✅ 在 `BridgeCoreParams` 增加 `worker_type` / `dir_path` 字段
8. ✅ 在 `BridgeCore` 增加 `environment_secret` 字段存储注册密钥

**测试**：1901 测试全部通过（+16 bridge 测试）

**已知缺口**：
- SessionSpawner 已与 BridgeCore 轮询循环集成 ✅（2026-04-21）
- 真实 SSE/WebSocket 连接未测试（需要真实 CCR 后端）
- `trusted_device.py` 中的 `get_trusted_device_token()` 仍为 stub（需要 secure storage 集成）

---

## P3 体验增强：Voice/STT 与 UI 组件

### 13. Voice/STT 服务 ✅

**已完成**：
- `services/voice_stream_stt/service.py` GrowthBook feature flag 集成（`tengu_cobalt_frost` → Nova 3）
- 修复 `_is_nova_3_enabled()` 使用 `get_feature_value("tengu_cobalt_frost", False)`
- 修复无效 Python 语法（`nonlocal` in lambda）- 重构 state 管理为 `state` dict

**涉及模块**：
- `services/voice_stream_stt/` — 已完成 GrowthBook 集成

**剩余**：
- `services/voice/` — 原生音频录制（audio-capture-napi）待实现

### 14. UI 组件补全 ✅

**已完成**：
- `services/doctor/` — Doctor 诊断服务（已有）
- `buddy/` — Companion 精灵系统（已有完整实现）
- `py_claw/ui/` — Textual REPL 屏幕 Phase 1-10 完成

**剩余**：
- `ResumeConversation.tsx` — 恢复对话屏幕（React/Ink 组件，高度依赖 TS app state，难以直接移植）

### 15. 其他 P3 缺口 ✅

**已完成**：
- `HybridTransport` — ✅ 已实现（`services/transports/hybrid.py`）
- `SerialBatchEventUploader` — ✅ 已实现（`services/transports/serial_batcher.py`）
- `WorkerStateUploader` — ✅ 已实现（`services/transports/`）
- 修复 `flush()` coroutine warning
- `webhookSanitizer` — ✅ 已实现（`services/bridge/webhook.py`）
- SSH 功能 — ✅ 已实现 asyncssh tunnel（`ssh/session.py`，2026-04-21）
- SessionSpawner + BridgeCore 集成 — ✅ 已完成（2026-04-21）

**缺失**：
- `trusted_device.py` 中的 `get_trusted_device_token()` 仍为 stub（需要 secure storage 集成）
- `services/voice/` — 原生音频录制（audio-capture-napi）待实现
- `ResumeConversation.tsx` — 恢复对话屏幕（React/Ink 组件，难以直接移植）
- Keybindings — 快捷键服务（部分在 `services/keybindings/` 已有）

---

1. **TUI 不要再走两套壳层**：现有 `PyClawApp` + `REPLScreen` 架构已收敛，继续在其内迭代
2. **Textual 不等于 Ink/React**：TS 的 hook/context 模式不能直接翻译，要按 Textual 的 widget/message/reactive 模型重新建模
3. **Python 测试注意编码**：Windows 下 pytest 可能遇到 GBK 解码问题，输出捕获时注意
4. **Shell completion Windows 降级**：Windows 下 `get_shell_type()` 返回 `UNKNOWN`，`get_shell_completions()` 静默返回空列表——预期行为
