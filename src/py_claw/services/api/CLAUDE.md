# services/api

[根文档](../../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **api**

# API 模块

本模块提供两类功能:

## 1. Anthropic API 客户端

来自 `ClaudeCode-main/src/services/api/claude.ts` 的 Python 原生实现。

## 2. 错误日志工具

来自 `ClaudeCode-main/src/utils/api.ts` 的错误日志和会话标题提取工具。

## 主要功能

### 错误日志 (api.ts / api.py)

- `get_log_display_title()` - 获取日志/会话显示标题，支持 fallback 逻辑
- `date_to_filename()` - 将日期转换为文件名安全格式
- `attach_error_log_sink()` - 附加错误日志接收器
- `log_error()` - 向多个目标记录错误
- `get_in_memory_errors()` - 获取内存中的错误列表
- `load_error_logs()` - 加载错误日志列表
- `get_error_log_by_index()` - 按索引获取错误日志
- `log_mcp_error()` - 记录 MCP 服务器错误
- `log_mcp_debug()` - 记录 MCP 调试信息
- `capture_api_request()` - 捕获最后的 API 请求

## 关键类型

- `ErrorInfo` - 内存中存储的错误信息
- `ErrorLogSink` - 错误日志接收器接口
- `LogOption` - 日志条目表示

## 相关文件

- `api.py` - 错误日志工具实现
- `client.py` - API 客户端实现
- `types.py` - API 类型定义
- `errors.py` - 错误类定义
- `streaming.py` - 流式解析工具
