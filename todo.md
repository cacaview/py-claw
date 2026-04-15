# TODO — py-claw 工作进度

> 更新日期：2026-04-15

---

## 已完成项目

### TUI Phase 1-5（全部完成 ✅）

| Phase | 内容 | 状态 |
|-------|------|------|
| TUI-0 | 收敛主路径，`PyClawApp` + `REPLScreen` 单一架构，标题 `py-claw`，去除默认 Footer，主输入切到 PromptInput | ✅ |
| TUI-1 | PromptInput 最小可用：slash command suggestions、inline ghost text、↑↓/Tab 键盘导航、suggestion list | ✅ |
| TUI-2 | 统一 SuggestionEngine：`COMMAND`/`PATH`/`SHELL_HISTORY`/`MID_INPUT_SLASH` 四类检测，mid-input slash detection | ✅ |
| TUI-3 | PromptFooter 动态 footer + HelpMenuDialog（`?` 键触发）+ `_format_prompt_hint` 上下文提示 | ✅ |
| TUI-4 | 4 个 overlay dialog（Ctrl+R History / Ctrl+P Quick Open / Ctrl+M Model / Ctrl+T Tasks）+ overlay 状态追踪 | ✅ |
| TUI-5 | State 化（TUIState + global store）、Layout 化（单一架构）、Vim mode（INSERT/NORMAL/VISUAL）、窄终端适配、pasted content、queue/stash prompt | ✅ |

关键文件变化：
- 新增 4 个 overlay dialog（`history_search`、`model_picker`、`quick_open`、`tasks_panel`）
- 新增 `state/tui_state.py`（TUIState + store helpers）
- 新增 `PromptFooter` widget、`HelpMenuDialog`
- 删除 `REPLApp` 独立壳层，统一为 `PyClawApp`
- `AppState` 新增 `tui: TUIState` 字段

### 其他已完成

- `/insights` 多阶段分析 pipeline（Phase A-H 完整，数据源切至 session_storage）
- bridge、remote、assistant、state 等子系统已确认与 TS 等效对齐

---

## 接下来可以做什么

### P1 — TUI 收尾与打磨

- **CommandDefinition adapter 化**：当前 `command_items` 用 dict，未来应收敛到正式 dataclass，提升类型安全
- **Recent usage 排序**：命令 suggestions 尚未按历史使用频率排序，接入 session history usage score 后可实现
- **Bridge/team/agent/task status pills**：Footer 右侧可增加状态图标（bridge 连接状态、agent 任务数等）

### P1/P2 — TUI 深度对齐

- **Prompt help 文案动态解析**：TS 侧 keybinding 文案来自 `getShortcutDisplay`，Python 侧目前硬编码，可考虑接入 `keymap` 服务
- **Shell completion**：当前已有基础 `get_shell_history_suggestions`，可扩展为完整 shell command completion（含 flags、subcommands）
- **Slack channel / agent at-mention suggestions**：TS 侧 `useTypeahead` 还处理 `@agent` 和 Slack channel 补全，Python 侧尚未实现
- **Speculation / pipelined suggestions**：TS 侧支持"边输入边预测"，Python 侧 `SpeculationState` 已存在但未接入 UI

### P2 — 运行时深度

- **`/insights` summarization 深度对齐**：当前 pipeline 中 `summarize_transcript_if_needed` 和 `generate_narrative_sections` 是 stub，可接入 LLM 深化
- **MCP 真实连接**：当前 `mcp/runtime.py` 是状态快照，可进一步实现真实 stdio/SSE/WebSocket 连接
- **Hook 深度**：commands hook、pre-commit hook 等尚未完全对齐

### P2 — 测试与可靠性

- **TUI 自动化测试**：当前只有手动 smoke test，可补 pytest textual 测试套件
- **CLI + TUI 集成测试**：端到端覆盖 `--tui` 启动 → prompt 提交 → 流式响应 → overlay 交互全路径

---

## 风险注意事项

1. **不要再在 `todo.md` 里写"未实现清单"**：绝大多数高信号功能已对齐或等效，剩余差异是"能力深度"和"实现形态"问题，不是"有没有"
2. **TUI 不要再走两套壳层**：现有 `PyClawApp` + `REPLScreen` 架构已收敛，继续在其内迭代
3. **Textual 不等于 Ink/React**：TS 的 hook/context 模式不能直接翻译，要按 Textual 的 widget/message/reactive 模型重新建模
