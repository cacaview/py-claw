# services/telemetry

## 模块职责

`services/telemetry/` 实现遥测和事件日志功能，对应 TypeScript `ClaudeCode-main/src/utils/telemetry/`。

## 关键函数

- `log_otel_event()` — 记录 OpenTelemetry 事件
- `set_event_logger()` / `get_event_logger()` — 事件日志器管理
- `redact_if_disabled()` — 根据用户提示日志设置决定是否脱敏
- `is_user_prompt_logging_enabled()` — 检查用户提示日志是否启用
- `get_telemetry_attributes()` — 获取通用遥测属性

## 遥测事件属性

- `event.name` — 事件名称
- `event.timestamp` — ISO 时间戳
- `event.sequence` — 会话内事件序号
- `prompt.id` — 提示 ID
- `workspace.host_paths` — 工作区目录
- `api.provider` — API provider

## 测试

- `tests/test_services_telemetry.py` — 遥测功能测试

## 变更记录

- 2026-04-14：新增 `services/telemetry/` 模块，实现 U13 功能
