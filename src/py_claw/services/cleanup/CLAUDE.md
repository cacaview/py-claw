# cleanup/

## 模块职责

`src/py_claw/services/cleanup/` 提供旧文件和缓存的清理工具，基于 `ClaudeCode-main/src/utils/cleanup.ts` 实现。

## 入口

- `__init__.py` - 公开 API 导出
- `cleanup.py` - 主要实现

## 核心功能

### 清理结果

- `CleanupResult` - 清理操作结果（messages 和 errors 计数）
- `add_cleanup_results()` - 合并两个清理结果

### 清理函数

- `get_cutoff_date()` - 获取清理截止日期
- `convert_filename_to_date()` - 转换文件名格式为日期
- `cleanup_old_message_files()` - 清理旧消息和错误日志
- `cleanup_old_session_files()` - 清理旧会话文件和 tool-results
- `cleanup_old_plan_files()` - 清理旧计划文件
- `cleanup_old_file_history_backups()` - 清理旧文件历史备份
- `cleanup_old_session_env_dirs()` - 清理旧会话环境目录
- `cleanup_old_debug_logs()` - 清理旧调试日志
- `cleanup_old_versions_throttled()` - 节流的旧版本清理

## 配置

- `cleanupPeriodDays` 设置控制保留期（默认 30 天）

## 文件名格式

清理函数处理的文件名格式：
`2024-01-15T10-30-00-000Z`（原始格式）
转换为：`2024-01-15T10:30:00.000Z`（ISO 格式）
