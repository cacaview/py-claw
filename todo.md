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

### P1 收尾与打磨

- **CommandDefinition adapter 化** ✅ — `CommandItem` dataclass 替代 `dict`，整条链路（`SuggestionEngine` / `generate_command_suggestions` / `get_best_command_match` / `HelpMenuDialog` / `_build_command_items`）已迁移至类型安全写法

---

## 接下来可以做什么

### P1 — 剩余收尾

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

1. **TUI 不要再走两套壳层**：现有 `PyClawApp` + `REPLScreen` 架构已收敛，继续在其内迭代
2. **Textual 不等于 Ink/React**：TS 的 hook/context 模式不能直接翻译，要按 Textual 的 widget/message/reactive 模型重新建模
3. **Python 测试注意编码**：Windows 下 pytest 可能遇到 GBK 解码问题，输出捕获时注意
