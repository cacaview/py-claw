[根目录](../../CLAUDE.md) > **ui**

# ui

## 模块职责

`py_claw/ui/` 是 Python 版 Claude Code 的 Textual 终端 UI 层，负责把 TypeScript Ink/React 组件重写为 Python Textual 组件。**已全部完成 Phase 1-5**。

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

### dialogs/ — 对话框 (20个)

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
| `WorktreeExitDialog` | 工作树退出确认对话框 |
| `DesktopHandoff` | Claude Desktop 会话交接对话框 |

## 测试与质量

- 当前只有 smoke test（手动运行 `--tui` 验证）
- 尚未有自动化测试

## 常见问题 (FAQ)

### 和 TypeScript 参考树的关系？
`ClaudeCode-main/src/components/design-system/` 和 `ClaudeCode-main/src/screens/` 是上游参考实现，UI 层需要逐一对应重写。

### 当前进度？
✅ 全部完成 — Phase 1 (核心屏幕) + Phase 2 (通用组件) + Phase 3 (对话框) + Phase 4 (高级组件) 全部实现完毕。

## 相关文件清单

- `textual_app.py` — 主应用入口
- `theme.py` — 主题系统
- `typeahead.py` — 统一 suggestion engine（SuggestionEngine + Suggestion + SuggestionType）
- `widgets/` — 设计系统组件 (21个，含 CommandSuggester）
- `screens/` — 屏幕组件 (5个)
- `dialogs/` — 对话框 (6个)

## 变更记录 (Changelog)

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
