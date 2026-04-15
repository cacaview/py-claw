# session_state/

## 模块职责

`src/py_claw/services/session_state/` 提供会话状态管理，基于 `ClaudeCode-main/src/utils/sessionState.ts` 实现。

## 入口

- `__init__.py` - 公开 API 导出
- `session_state.py` - 主要实现

## 核心功能

### Session State

- `get_session_state()` - 获取当前会话状态
- `notify_session_state_changed()` - 通知会话状态变更
- `set_session_state_changed_listener()` - 注册状态变更监听器

### Session Metadata

- `notify_session_metadata_changed()` - 通知会话元数据变更
- `set_session_metadata_changed_listener()` - 注册元数据变更监听器

### Permission Mode

- `notify_permission_mode_changed()` - 通知权限模式变更
- `set_permission_mode_changed_listener()` - 注册权限模式变更监听器

## 类型

- `SessionState` - 会话状态类型（'idle' | 'running' | 'requires_action'）
- `RequiresActionDetails` - pending action 详情
- `SessionExternalMetadata` - 会话外部元数据

## 监听器

- `SessionStateChangedListener` - 状态变更回调
- `SessionMetadataChangedListener` - 元数据变更回调
- `PermissionModeChangedListener` - 权限模式变更回调

## 状态流

1. `idle` - 会话空闲
2. `running` - 会话运行中
3. `requires_action` - 需要用户操作（包含 pending action details）
