# suggestions/

## 模块职责

`src/py_claw/services/suggestions/` 提供命令/shell历史/目录补全建议，基于 `ClaudeCode-main/src/utils/suggestions/` 实现。

## 入口

- `__init__.py` - 公开 API 导出
- `suggestions.py` - 主要实现

## 核心功能

### 目录补全

- `parse_partial_path()` - 解析部分路径为目录和前缀组件
- `get_directory_completions()` - 获取目录补全建议
- `scan_directory()` - 扫描目录返回子目录（使用 LRU 缓存）
- `is_path_like_token()` - 检查字符串是否像路径
- `clear_directory_cache()` - 清除目录缓存

### 路径补全

- `get_path_completions()` - 获取文件和目录的路径补全建议
- `scan_directory_for_paths()` - 扫描目录返回文件和子目录
- `clear_path_cache()` - 清除路径缓存

### 命令补全

- `is_command_input()` - 检查输入是否为命令（以 / 开头）
- `get_command_args()` - 检查命令输入是否有参数
- `format_command()` - 格式化命令
- `find_mid_input_slash_command()` - 查找输入中间位置的 slash 命令
- `get_best_command_match()` - 查找最佳命令匹配
- `generate_command_suggestions()` - 生成命令建议
- `find_slash_command_positions()` - 查找文本中所有 /command 模式位置

### Shell 历史

- `get_shell_history_completion()` - 从历史记录获取补全
- `clear_shell_history_cache()` - 清除历史缓存

## 类型

- `DirectoryEntry` - 目录条目
- `PathEntry` - 路径条目（文件或目录）
- `PathCompletionOptions` - 路径补全选项
- `CommandSuggestionItem` - 命令建议条目
- `MidInputSlashCommand` - 中间输入的 slash 命令
- `CommandMatch` - 命令匹配结果
- `ShellHistoryMatch` - Shell 历史匹配结果

## 缓存

- 使用 LRU 缓存避免重复文件系统调用
- 缓存大小：500 条目
- 缓存 TTL：5 分钟（目录/路径），60 秒（Shell 历史）
