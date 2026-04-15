# services/debug

[根文档](../../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **debug**

# Debug 模块

Note: 此模块命名对应 TypeScript 源文件 `src/utils/log.ts`(原名 debug.ts)。
实际功能是调试日志记录,入口点为 `log.py`。

## 模块职责

本模块是 `log.py` 的别名重导出,用于匹配 TypeScript 源文件结构。

## 主要功能

所有功能通过 `log.py` 实现:

- `DebugLogLevel` - 日志级别枚举
- `is_debug_mode()` - 调试模式检测
- `enable_debug_logging()` - 启用调试日志
- `log_for_debugging()` - 记录调试信息
- `get_debug_log_path()` - 获取调试日志路径
- `log_ant_error()` - Ants 专用错误记录

## 相关文件

- `debug.py` - 重导出 `log` 模块
- `../log/log.py` - 实际实现
