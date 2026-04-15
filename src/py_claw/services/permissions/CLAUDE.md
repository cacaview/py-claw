# services/permissions

## 模块职责

`services/permissions/` 实现权限相关的工具函数，对应 TypeScript `ClaudeCode-main/src/utils/permissions/`。

## 子模块

- `auto_mode_state.py` — Auto mode 状态跟踪
- `classifier_decision.py` — YOLO 分类器决策
- `path_validation.py` — 路径安全验证
- `permission_explainer.py` — 权限结果解释

## 关键函数

### auto_mode_state.py

- `is_auto_mode_active()` — 检查 auto mode 是否激活
- `set_auto_mode_active()` / `clear_auto_mode()` — 管理 auto mode 状态

### classifier_decision.py

- `is_auto_mode_allowlisted_tool()` — 检查工具是否在安全白名单
- `classify_yolo_action()` — YOLO 分类器（stub 实现）

### path_validation.py

- `path_in_allowed_working_path()` — 检查路径是否在允许的工作目录内
- `check_path_safety_for_auto_edit()` — 检查自动编辑路径安全性
- `is_protected_namespace()` — 检查是否为受保护的系统目录

### permission_explainer.py

- `explain_permission_result()` — 生成人类可读的权限结果说明
- `format_permission_rule()` — 格式化权限规则字符串

## 测试

- `tests/test_services_permissions.py` — 权限工具函数测试

## 变更记录

- 2026-04-14：新增 `services/permissions/` 模块，实现 U12 功能
