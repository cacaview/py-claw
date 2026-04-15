[根目录](../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **settings**

# settings

## 模块职责

处理 `.claude/settings.json`、`.claude/settings.local.json`、flag settings、policy settings 的加载、校验、过滤和深合并，是权限与运行态配置的基础层。

## 入口与启动

- 主入口：`loader.py::get_settings_with_sources`
- 校验：`validation.py::validate_settings_data` / `validate_settings_text`
- 合并：`merge.py::merge_settings`
- 类型：`types.py::SettingsModel`

## 对外接口

- 支持五类来源：`userSettings`、`projectSettings`、`localSettings`、`flagSettings`、`policySettings`
- 返回结构：`SettingsLoadResult(effective, sources, issues)`
- 会过滤非法 permission rules，并把问题转成 `SettingsValidationIssue`

## 关键依赖与配置

- 约定路径：`~/.claude/settings.json`、`<cwd>/.claude/settings.json`、`<cwd>/.claude/settings.local.json`
- 深合并策略：字典递归合并，标量/列表后者覆盖前者

## 数据模型

- `SettingsModel`
- `PermissionsSettings`
- `SettingsValidationIssue`
- `SettingsLoadResult`

## 测试与质量

- 已确认测试覆盖 settings source 优先级、非法规则过滤、权限相关边界值
- 缺口：未深扫针对 hooks/agents/skills/mcp 全字段的系统性案例

## 常见问题 (FAQ)

### settings 是追加还是覆盖？
字典递归合并，后来源覆盖先来源。

### 非法 permission rule 会怎样？
会被跳过，同时记录 issue，而不是直接让整个 settings 失效。

## 相关文件清单

- `loader.py`
- `validation.py`
- `merge.py`
- `types.py`
- `__init__.py`

## 变更记录 (Changelog)

- 2026-04-08 18:07:18：创建 `settings` 模块文档。