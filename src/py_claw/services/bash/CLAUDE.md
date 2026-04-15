# bash/

## 模块职责

`src/py_claw/services/bash/` 提供 shell  quoting 和 completion 工具，基于 `ClaudeCode-main/src/utils/bash/` 实现。

## 入口

- `__init__.py` - 公开 API 导出
- `bash.py` - 主要实现

## 核心功能

### Shell Quoting

- `try_parse_shell_command()` - 解析 shell 命令为 tokens
- `try_quote_shell_args()` - 安全地引用 shell 参数
- `quote_shell_args()` - 带回退的 shell 参数引用
- `has_malformed_tokens()` - 检测 shell-quote 误解的畸形 token
- `has_shell_quote_single_quote_bug()` - 检测 shell-quote 单引号 bug

### Shell Completion

- `get_shell_completions()` - 获取 shell 补全建议
- `ShellCompletionType` - 补全类型（command/variable/file）

### Shell History

- `get_shell_history_completion()` - 从历史记录获取补全
- `clear_shell_history_cache()` - 清除历史缓存
- `prepend_to_shell_history_cache()` - 添加到历史缓存

## 类型

- `ParseEntry` - 解析的 token 基类
- `StringEntry` - 字符串 token
- `OpEntry` - 操作符 token（|, ||, &&, ;）
- `ShellHistoryMatch` - 历史记录匹配结果

## 依赖

- `shlex` - Python 标准库用于 shell 引用
