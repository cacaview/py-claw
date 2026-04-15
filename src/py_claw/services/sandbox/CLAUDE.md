# services/sandbox

## 模块职责

`services/sandbox/` 实现沙箱适配器，封装 sandbox-runtime 并集成 Claude CLI 特有功能，对应 TypeScript `ClaudeCode-main/src/utils/sandbox/`。

## 子模块

- `sandbox_adapter.py` — 沙箱配置转换和集成

## 关键函数

### sandbox_adapter.py

- `is_supported_platform()` — 检查当前平台是否支持沙箱
- `is_sandboxing_enabled()` — 检查沙箱是否启用
- `is_platform_in_enabled_list()` — 检查平台是否在 enabledPlatforms 列表中
- `get_sandbox_unavailable_reason()` — 获取沙箱不可用的原因
- `check_dependencies()` — 检查沙箱依赖是否满足
- `resolve_path_pattern_for_sandbox()` — 解析 Claude CLI 特有路径模式
- `resolve_sandbox_filesystem_path()` — 解析沙箱文件系统路径

## SandboxManager 接口

- `initialize()` — 初始化沙箱
- `wrap_with_sandbox()` — 用沙箱包装命令
- `cleanup_after_command()` — 命令后清理
- `reset()` — 重置沙箱状态
- `get_excluded_commands()` — 获取排除在沙箱外的命令列表

## 测试

- `tests/test_services_sandbox.py` — 沙箱功能测试

## 变更记录

- 2026-04-14：新增 `services/sandbox/` 模块，实现 U15 功能
