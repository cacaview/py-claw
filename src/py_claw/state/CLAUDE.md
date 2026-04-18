[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **state**

# state

## 模块职责

`py_claw/state/` 提供 React-like状态管理模式，基于 Observable 模式和线程安全的观察者模式。用于替代 py_claw 其他模块中简单的单例 State 类，提供完整的订阅/发布能力和函数式更新。

## 架构概览

```
state/
├── observable.py      # Observable/ChangeDetector 基类
├── app_state.py      # AppState dataclass (60+ 字段) + TUIState
├── store.py          # 全局 Store 单例
├── selectors.py      # 选择器函数
├── observers.py      # 状态变更观察者
├── tui_state.py      # TUI State helpers (TUIState + store helpers)
└── teammate_helpers.py  # teammate view helpers (enterTeammateView/exitTeammateView)
```

## 核心概念

### Observable 模式

类似 React 的 `useSyncExternalStore`：
- `subscribe(callback)` 返回取消订阅函数
- `get_snapshot()` 返回当前状态快照
- `update(updater)` 函数式更新

### ChangeDetector

线程安全的 Observable 实现：
- `RLock` 保证线程安全
- 函数式更新模式
- 变更通知机制

### Store

全局状态单例：
- 集中式状态访问
- 中间件支持
- 选择器派生计算

## 导出 API

### Observable (observable.py)

| 类/函数 | 说明 |
|---------|------|
| `Observable` | 抽象基类 |
| `ChangeDetector` | 线程安全状态持有者 |
| `ObservableState` | dataclass 响应式封装 |

### AppState (app_state.py)

| 类/函数 | 说明 |
|---------|------|
| `AppState` | 全局应用状态 dataclass (60+ 字段) |
| `UIState` | UI 相关状态（展开视图、footer 选择等） |
| `MCPState` | MCP 客户端/工具/命令/资源状态 |
| `PluginState` | 插件启用/禁用/错误状态 |
| `NotificationState` | 通知状态 |
| `ElicitationState` | 权限请求 elicitation 状态 |
| `PromptSuggestionState` | Prompt 建议状态 |
| `SessionHooksState` | Session hooks 状态 |
| `SpeculationState` | 推测执行状态 |
| `FileHistoryState` | 文件历史状态 |
| `AttributionState` | Attribution 状态 |
| `AgentDefinitionsState` | Agent 定义状态 |
| `SkillImprovementState` | Skill 改进建议状态 |
| `InitialMessageState` | 初始消息状态 |
| `PendingPlanVerificationState` | 待验证计划状态 |
| `WorkerSandboxPermissionsState` | Worker 沙箱权限状态 |
| `PendingWorkerRequestState` | 待处理 worker 请求状态 |
| `PendingSandboxRequestState` | 待处理沙箱请求状态 |
| `ReplContextConsoleState` | REPL 控制台状态 |
| `ReplContextState` | REPL VM 上下文状态 |
| `TeammateInfo` | Teammate 信息 |
| `TeamContextState` | 团队上下文状态 |
| `StandaloneAgentContextState` | 独立 Agent 上下文状态 |
| `InboxMessage` | 收件箱消息结构 |
| `InboxState` | 收件箱状态 |
| `ComputerUseMcpState` | Computer Use MCP 状态 |
| `TungstenSessionState` | Tungsten/tmux 会话状态 |
| `TungstenLastCommandState` | Tungsten 上次命令状态 |
| `BuddyNotification` | Buddy 通知结构 |
| `NotificationTrigger` | Buddy 触发位置结构 |
| `BuddyNotificationManager` | Buddy 通知管理器 |
| `TUIState` | TUI 状态（prompt_mode/vim_mode/suggestions/queued_prompts/stashed_prompt/pasted_content/narrow_terminal） |
| `create_default_app_state()` | 创建默认状态 |

### Store (store.py)

| 类/函数 | 说明 |
|---------|------|
| `Store` | 全局 Store 类 |
| `create_store()` | 创建 Store 实例 |
| `get_global_store()` | 获取全局单例 |

### Selectors (selectors.py)

| 函数 | 说明 |
|------|------|
| `get_viewed_teammate_task()` | 获取当前查看的 teammate 任务 |
| `get_active_agent_for_input()` | 获取活跃 agent ID |
| `get_visible_tasks()` | 获取可见任务列表 |
| `get_task_count()` | 获取任务数量 |
| `is_bridge_connected()` | 检查 Bridge 连接状态 |
| `is_thinking_mode_enabled()` | 检查思考模式 |
| `get_expanded_view()` | 获取当前展开视图 |
| `get_mcp_client_count()` | 获取 MCP 客户端数量 |
| `get_enabled_plugin_count()` | 获取启用插件数量 |
| `get_plugin_errors()` | 获取插件错误 |

### TUI State (tui_state.py)

| 类/函数 | 说明 |
|---------|------|
| `TUIState` | TUI 状态 dataclass |
| `TUIStateSnapshot` | TUI 状态快照 |
| `TUIStateSubscriber` | TUI 状态订阅 helper（类似 `useSyncExternalStore`） |
| `update_tui_prompt_mode()` | 发布 prompt mode 变更 |
| `update_tui_vim_mode()` | 发布 vim mode 变更 |
| `update_tui_suggestions()` | 发布 suggestion 状态变更 |
| `update_tui_speculation()` | 发布 speculation 状态（status/boundary/tool_count） |
| `update_tui_prompt_value()` | 发布当前 prompt 值 |
| `queue_prompt()` / `dequeue_prompt()` | 队列命令管理 |
| `stash_prompt()` | 暂存当前 prompt |
| `set_pasted_content()` | 设置粘贴内容标识 |
| `set_narrow_terminal()` | 设置窄终端模式 |
| `add_active_overlay()` / `remove_active_overlay()` | overlay 状态同步 |
| `update_tui_speculation()` | 发布 speculation 状态（status/boundary/tool_count） |

### Observers (observers.py)

| 类/函数 | 说明 |
|---------|------|
| `StateObserver` | 状态观察者抽象基类 |
| `on_state_change()` | 默认状态变更处理器 |
| `register_observer()` | 注册观察者 |

### Teammate Helpers (teammate_helpers.py)

| 类/函数 | 说明 |
|---------|------|
| `enter_teammate_view()` | 进入 teammate 视图，设置 retain 状态 |
| `exit_teammate_view()` | 退出 teammate 视图，释放任务 |
| `stop_or_dismiss_agent()` | 停止或 Dismiss agent |

## 使用示例

```python
from py_claw.state import (
    get_global_store,
    create_store,
)

# 获取全局 Store
store = get_global_store()

# 订阅状态变更
def on_change():
    print("State changed!")

unsubscribe = store.subscribe(on_change)

# 函数式更新
store.update(lambda s: _with_thinking(s, True))

# 使用选择器
is_thinking = store.select(lambda s: s.thinking_enabled)

# 取消订阅
unsubscribe()
```

## 与 Textual 集成

Textual 的 `@reactive` 装饰器提供类似的响应式能力：

```python
from textual.reactive import reactive
from textual import App

class MyApp(App):
    count = reactive(0)

    def watch_count(self, old_value, new_value):
        # 类似 observer
        self.notify(f"Count changed: {new_value}")
```

## React 模式映射

| React/TypeScript | py_claw/state |
|-----------------|----------------|
| `Store<T>` | `ChangeDetector<T>` |
| `useSyncExternalStore` | `subscribe()` + `get_snapshot()` |
| `AppState` | `AppState` dataclass |
| `AppStateStore` | `Store` 单例 |
| `selectors.ts` | `selectors.py` |
| `onChangeAppState` | `observers.py` |

## 变更记录 (Changelog)

- 2026-04-15：TUI-5 新增 `tui_state.py`（TUIState + TUIStateSubscriber + store helpers）；`AppState` 新增 `tui: TUIState` 字段（含 prompt_mode/vim_mode/suggestions/queued_prompts/stashed_prompt/pasted_content/narrow_terminal）
- 2026-04-14：新增 `teammate_helpers.py` 模块，实现 `enter_teammate_view()`/`exit_teammate_view()`/`stop_or_dismiss_agent()` 函数；扩展 AppState 至 60+ 字段匹配 TS 实现。1440 测试全部通过。
- 2026-04-14：新增 `state/` 模块，实现 Observable 模式 + AppState dataclass + Store 单例 + 选择器 + 观察者，21 个测试全部通过。
