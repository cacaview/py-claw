# services/log

[根文档](../../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **log**

# Log 模块

调试日志工具模块,来自 `ClaudeCode-main/src/utils/log.ts`。

## 主要功能

### 调试日志级别

- `DebugLogLevel` - 枚举类型: VERBOSE, DEBUG, INFO, WARN, ERROR
- `get_min_debug_log_level()` - 获取最小日志级别(默认 DEBUG)
- `LEVEL_ORDER` - 日志级别顺序映射

### 调试模式检测

- `is_debug_mode()` - 检测调试模式是否启用
- `enable_debug_logging()` - 启用调试日志记录(中途启用)
- `get_debug_filter()` - 从命令行解析调试过滤器
- `is_debug_to_stderr()` - 检查是否输出到 stderr
- `get_debug_file_path()` - 获取调试日志文件路径

### 消息过滤

- `should_log_debug_message()` - 判断是否应记录消息
- `_matches_debug_filter()` - 检查消息是否匹配过滤器

### 格式化输出

- `set_has_formatted_output()` - 设置格式化输出状态
- `get_has_formatted_output()` - 获取格式化输出状态

### 日志记录

- `log_for_debugging()` - 记录调试信息
- `get_debug_log_path()` - 获取调试日志路径
- `flush_debug_logs()` - 刷新待处理的调试日志
- `log_ant_error()` - 仅记录 Ants 错误

## 环境变量

- `CLAUDE_CODE_DEBUG_LOG_LEVEL` - 最小日志级别
- `DEBUG` - 启用调试模式
- `DEBUG_SDK` - 启用 SDK 调试
- `CLAUDE_CODE_DEBUG_LOGS_DIR` - 调试日志目录
- `NODE_ENV` - 环境(测试模式检查)

## CLI 参数

- `--debug`, `-d` - 启用调试模式
- `--debug-to-stderr`, `-d2e` - 输出到 stderr
- `--debug=pattern` - 设置调试过滤器
- `--debug-file=path` - 设置调试日志文件

## 相关文件

- `log.py` - 调试日志实现
