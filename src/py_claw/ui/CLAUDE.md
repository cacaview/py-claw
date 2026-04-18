[根目录](../../CLAUDE.md) > **ui**

# ui

## 模块职责

`py_claw/ui/` 是 Python 版 Claude Code 的 Textual 终端 UI 层，负责把 TypeScript Ink/React 组件重写为 Python Textual 组件。**已全部完成 Phase 1-5，主 REPL 已接入核心 overlay 并补齐自动化覆盖，小终端 compact layout 与主流程快捷键面也已对齐。**

主要目标：
- REPL 主界面与消息列表
- Dialog / Pane / Tabs 等设计系统组件
- Doctor / Resume 等辅助屏幕

## 入口与启动

- 主入口：`textual_app.py` 的 `run_textual_ui(state, query_runtime, *, prompt)`
- CLI 入口：`py_claw/cli/main.py` 支持 `--tui` flag 启动 Textual UI

## 对外接口

- `run_textual_ui(state, query_runtime, *, prompt)` — 启动 Textual 应用
- `REPLScreen` — 主 REPL 屏幕组件

## 关键依赖与配置

- `textual>=0.50`
- 依赖 `py_claw.cli.runtime.RuntimeState`
- 依赖 `py_claw.query.QueryRuntime`

## 已实现组件

### widgets/ — 设计系统组件 (21个)

| 组件 | 说明 | 参考文件 |
|------|------|---------|
| `Dialog` | 确认/取消对话框 | `design-system/Dialog.tsx` |
| `Pane` | 彩色边框内容容器 | `design-system/Pane.tsx` |
| `Tabs` | 键盘优先标签导航 | `design-system/Tabs.tsx` |
| `ThemedBox` | 主题感知容器 | `design-system/ThemedBox.tsx` |
| `ThemedText` | 主题感知文本 | `design-system/ThemedText.tsx` |
| `Divider` | 分割线 | `design-system/Divider.tsx` |
| `ProgressBar` | 进度条 | `design-system/ProgressBar.tsx` |
| `StatusIcon` | 状态图标 | `design-system/StatusIcon.tsx` |
| `StatusLine` | 状态行 | `design-system/StatusLine.tsx` |
| `FuzzyPicker` | 模糊搜索选择器 | `design-system/FuzzyPicker.tsx` |
| `ListItem` | 可复用列表项 | `design-system/ListItem.tsx` |
| `MessageList` | 消息列表 | `MessageList.tsx` |
| `StructuredDiff` | 结构化 diff 显示 | `StructuredDiff.tsx` |
| `VirtualMessageList` | 虚拟化消息列表 | `VirtualMessageList.tsx` |
| `FeedbackDialog` | 反馈对话框 | `Feedback.tsx` |
| `StarRating` | 星级评分 | `Feedback.tsx` |
| `ShareDialog` | 分享对话框 | `ShareDialog.tsx` |
| `CustomSelect` | 键盘导航选择器（单选/多选） | `CustomSelect/select.tsx` |
| `PromptInput` | 增强提示输入（含模式指示/历史/slash命令建议/键盘导航/inline ghost text） | `PromptInput/PromptInput.tsx` |
| `PromptFooter` | 动态 footer（mode indicator/hints/suggestion list/help row） | `PromptInputFooter.tsx` |

### screens/ — 屏幕 (5个)

| 屏幕 | 说明 | 参考文件 |
|------|------|---------|
| `REPLScreen` | REPL 主屏幕 | `REPL.tsx` |
| `DoctorScreen` | 诊断屏幕 | `Doctor.tsx` |
| `ResumeScreen` | 会话恢复屏幕 | `ResumeConversation.tsx` |
| `SessionScreen` | 会话管理屏幕 | `SessionScreen.tsx` |
| `PlanModeScreen` | Plan Mode 屏幕 | `PlanMode.tsx` |

### dialogs/ — 对话框 (16+个)

| 对话框 | 说明 |
|--------|------|
| `PermissionDialog` | 权限请求对话框 |
| `AgentsMenu` | Agent 管理菜单 |
| `AgentEditor` | Agent 编辑器 |
| `ConfigDialog` | 配置编辑器 |
| `ContextDialog` | Context 查看器 |
| `MCPServerDialog` | MCP 服务器管理 |
| `SkillsDialog` | Skills 管理 |
| `TrustDialog` | 工作空间信任确认对话框 |
| `WorkflowMultiselectDialog` | GitHub 工作流多选对话框 |
| `HelpMenuDialog` | 帮助菜单（显示 slash commands 和快捷键，`?` 触发） |
| `HistorySearchDialog` | Shell 历史搜索（Ctrl+R 触发） |
| `ModelPickerDialog` | 模型选择器（Ctrl+M 触发） |
| `QuickOpenDialog` | 快速文件搜索（Ctrl+P 触发） |
| `TasksPanel` | 后台任务面板（Ctrl+T 触发） |
| `PromptDialog` | 用户提问/elicitation 对话框 |
| `WorktreeExitDialog` | 工作树退出确认对话框 |
| `DesktopHandoff` | Claude Desktop 会话交接对话框 |

## 测试与质量

- 已有自动化 TUI 测试：`tests/test_tui/` + `tests/test_tui_textual.py`
- 覆盖基础挂载、PromptInput 交互、主 REPL overlay 生命周期、dialog 最小交互、suggestion UX、窄屏/矮屏 compact layout，以及主流程快捷键面一致性（help / status / footer / `Shift+Tab` mode cycle）
- 仍建议在重要 UI 变更后手动运行 `--tui` 做 smoke 验证

## 常见问题 (FAQ)

### 和 TypeScript 参考树的关系？
`ClaudeCode-main/src/components/design-system/` 和 `ClaudeCode-main/src/screens/` 是上游参考实现，UI 层需要逐一对应重写。

### 当前进度？
✅ 全部完成 — Phase 1 (核心屏幕) + Phase 2 (通用组件) + Phase 3 (对话框) + Phase 4 (高级组件) + Phase 5（主 REPL overlay 自动化覆盖）已落地；`<80` / `<20` 小终端现已改为 compact layout，而非直接隐藏 prompt/footer 信息面；主流程 shortcut surface 现已对齐到真实 Python 绑定，并补齐 `Shift+Tab` mode cycle。

### 小终端下现在会直接隐藏 footer 吗？
不会。当前 `<80` 宽与 `<20` 高会进入 compact layout：优先压缩 `PromptInput` / `PromptFooter` 的 mode、hint、suggestion viewport 与 help row，只在最紧张的 `tight` 模式下隐藏次要信息，不再整块隐藏 footer。

## 相关文件清单

- `textual_app.py` — 主应用入口
- `theme.py` — 主题系统
- `typeahead.py` — 统一 suggestion engine（SuggestionEngine + Suggestion + SuggestionType）
- `widgets/` — 设计系统组件 (21个，含 CommandSuggester）
- `screens/` — 屏幕组件 (5个)
- `dialogs/` — 对话框与 overlay 组件（help/history/model/quick-open/tasks/prompt/permission 等）

## 变更记录 (Changelog)

- 2026-04-18：Speculation UI 集成完成 — `PromptFooter` 新增 speculation status pills 展示（`speculation_status`/`boundary`/`tool_count`）；`REPLScreen` 新增 `set_speculation_state()` 方法；`textual_app.py` 注册 `_register_speculation_callback()` 将 SpeculationService 状态变更同步到 UI footer；`tui_state.py` 新增 `update_tui_speculation()` helper
- 2026-04-16：主交互快捷键面对齐完成 — `services/keybindings/service.py` 新增 centralized shortcut hints，统一 help menu / status line / footer 文案；`PromptInput` 新增 `Shift+Tab` mode cycle（`normal → plan → auto → bypass → normal`）；`REPLScreen` 同步 prompt mode 变化到 footer / TUI store；新增针对 shortcut surface 的 TUI 回归覆盖 — `services/keybindings/service.py` 新增 centralized shortcut hints，统一 help menu / status line / footer 文案；`PromptInput` 新增 `Shift+Tab` mode cycle（`normal → plan → auto → bypass → normal`）；`REPLScreen` 同步 prompt mode 变化到 footer / TUI store；新增针对 shortcut surface 的 TUI 回归覆盖，验证 mode cycle 与 help/status/footer 一致性
- 2026-04-16：窄屏 / 矮屏布局策略优化完成 — `textual_app.py` 移除 `<80` / `<20` 时对 `#pi-mode-bar` 与 `#repl-footer` 的整块隐藏；`REPLScreen` 新增 compact layout 分发；`PromptInput` / `PromptFooter` 新增 `compact_mode`（`full` / `narrow` / `short` / `tight`），缩短 mode/hint/help 文案并收缩 suggestion viewport；新增 responsive 回归覆盖，验证 `<80`、`<20` 与 `<80 && <20` 下最小可用 prompt/footer 仍可见
- 2026-04-16：主 REPL overlay 覆盖面补齐 — 新增 `tests/test_tui/test_overlays.py`，覆盖 Help / History Search / Quick Open / Model Picker / TasksPanel 的打开、关闭、互斥和选择结果回填；同时补 `PromptDialog`、`PermissionDialog` 最小交互测试；修复 `HelpMenuDialog.action_cancel()` 未 remove、自定义 `ListItem` id 未做 Textual-safe 规整、`PermissionDialog` 回调在 `Dialog.__init__()` 后被覆盖，以及 `services/model/model.py` 中 opus 常量命名/缩进问题
- 2026-04-16：Prompt suggestion UX 收敛完成 — `PromptInput` 移除 `#pi-suggestion-list` 重复渲染，改由 `PromptFooter` 作为单一建议展示面；`REPLScreen.set_suggestion_items()` 改为只更新 footer；`get_suggestions()` 新增 `AGENT`、`CHANNEL` 类型处理；`detect_type()` 修复 bare `#` 检测（正则改为 `?` 可选）；`group(2)` 为 `None` 的边界情况修复；PageUp 行为统一为不 wrap；新增 `tests/test_typeahead.py`（42 个测试）
- 2026-04-15：TUI-5 State化/Layout化/高级 parity 完成 — 新增 `state/tui_state.py`（TUIState + TUIStateSubscriber + store helpers）；`AppState` 新增 `tui: TUIState` 字段；`PromptInput` vim mode 增强（INSERT/NORMAL/VISUAL 切换、`VimModeChanged` 消息、`pasted_content_label`）；`REPLScreen` 状态发布至 global store（prompt_mode/vim_mode/suggestions）；窄终端适配（`< 80` 宽自动隐藏 mode bar 和 footer）；HelpMenuDialog 扩展 vim 快捷键说明
- 2026-04-15：TUI-4 Overlay/Dialog/Search 面板接入完成 — 新增 4 个 overlay dialog（`HistorySearchDialog`、`ModelPickerDialog`、`QuickOpenDialog`、`TasksPanel`）；REPLScreen 新增 Ctrl+R/P/M/T 快捷键 + overlay 状态追踪（`_active_overlay`/`_overlay_ids`）；`PyClawApp` 同步接入 4 个新 BINDINGS + action handler；HelpMenuDialog 快捷键说明扩展
- 2026-04-15：TUI-3 Footer/Help/Status 动态化完成 — 新增 `PromptFooter`（`widgets/prompt_footer.py`）：动态 footer，含 mode indicator / contextual hints / suggestion list / help shortcut row；新增 `HelpMenuDialog`（`dialogs/help.py`）：`?` 键触发帮助菜单，显示所有 slash commands 和快捷键；`REPLScreen` 完成 `PromptFooter` 接入、`HelpToggled` 嵌套消息路由（`__qualname__` 检测）、`set_mode/set_status/set_loading/set_suggestions` 全部接线；修复 `$text-dim` CSS 变量未定义问题（改为 `$text-muted`）
- 2026-04-15：TUI-2 SuggestionEngine 统一化完成 — 新增 `ui/typeahead.py`（`SuggestionEngine` + `Suggestion` dataclass + `SuggestionType` enum），统一 orchestrating slash commands / path / shell history；`PromptInput` 重构为 `suggestion_engine: SuggestionEngine`；支持 mid-input slash detection、path-like token completion、`_format_prompt_hint` 按类型上下文切换
- 2026-04-15：TUI-1 PromptInput 最小可用对齐完成 — 新增 `CommandSuggester`（Textual `Suggester` 实现）+ inline ghost text（`/he` → `/help ` 光标后显示 `lp `）+ `Tab`/`→` 接受机制 + `↑↓` 建议列表循环 + `#pi-suggestion-list` 渲染 + `suggestion_items`/`selected_index` reactive 状态
- 2026-04-14：新增 CustomSelect 和 PromptInput — 键盘导航选择器与增强输入组件（P1 UI 缺口全部补齐）
- 2026-04-14：P2 辅助功能全部完成 — TrustDialog、WorkflowMultiselectDialog、WorktreeExitDialog、DesktopHandoff、ErrorBoundary
- 2026-04-13：Phase 1 全部完成 — 新增 REPLScreen
- 2026-04-13：Phase 4 完成 — VirtualMessageList、FeedbackDialog、ShareDialog、SessionScreen、PlanModeScreen
- 2026-04-13：Phase 3 完成 — PermissionDialog、AgentsMenu、AgentEditor、ConfigDialog、ContextDialog、MCPServerDialog、SkillsDialog
- 2026-04-13：Phase 2 完成 — FuzzyPicker、ListItem、StatusLine、MessageList、StructuredDiff
- 2026-04-13：Phase 1 完成 — theme、Pane、Dialog、Tabs、ThemedBox、ThemedText、Divider、ProgressBar、StatusIcon、DoctorScreen、ResumeScreen
