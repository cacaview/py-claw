[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **utils**

# utils

## 模块职责

`py_claw/utils/` 是 Python 版 Claude Code 运行时的通用工具层，提供跨模块复用的轻量工具函数。与 `services/` 的区别是：`services/` 承担运行时服务能力（API、OAuth、LSP 等），`utils/` 提供纯函数式工具和基础类型封装。

## 子模块导航

### 基础工具

- `hooks.py` — Hook 相关工具函数
- `errors.py` — 错误处理工具、异常类型、错误格式化
- `json.py` — JSON 解析/序列化辅助函数
- `path.py` — 跨平台路径操作工具
- `env.py` — 环境变量检测与 Claude 配置目录

### U1-U10 新增工具（对应 ClaudeCode-main/src/utils/）

- `auth.py` — 认证工具（API key、OAuth token、云服务商认证）
- `api.py` — API 工具（tool schema、system prompt、context metrics）
- `log.py` — 日志工具（错误日志、会话日志、内存错误队列）
- `debug.py` — 调试日志（分级日志、缓冲写入、debug file/filter）
- `stats.py` — 统计聚合（session 统计、streak 计算、daily activity）
- `session_state.py` — 会话状态管理（idle/running/requires_action 转换）
- `cron.py` — Cron 表达式解析与 next-run 计算
- `attachments.py` — 消息附件处理（文本/图片粘贴、尺寸、token估算）
- `extra_usage.py` — 额外使用量计费判断
- `fast_mode.py` — 快速模式状态管理
- `background_housekeeping.py` — 后台维护任务
- `exec_file_no_throw.py` — 不抛异常的文件执行
- `early_input.py` — 早期输入处理
- `embedded_tools.py` — 嵌入式工具
- `auth_portable.py` — 便携式认证
- `auth_file_descriptor.py` — 文件描述符认证
- `cleanup.py` — 清理工具（旧日志、session 文件、debug logs、npm cache）
- `bash/` — Shell 工具子包
  - `shell_quote.py` — Shell 参数引号转义与解析
  - `shell_completion.py` — Shell 补全生成（bash/zsh）
- `suggestions/` — 建议补全子包
  - `command_suggestions.py` — Slash command 模糊匹配与建议
  - `shell_history_completion.py` — Shell 历史补全
  - `directory_completion.py` — 目录/文件路径补全

## 导出 API

### 错误工具 (errors)

| 函数/类 | 说明 |
|---------|------|
| `ErrorContext` | 错误上下文 dataclass |
| `error_message()` | 从任意对象提取错误消息字符串 |
| `get_error_context()` | 获取详细错误上下文 |
| `CliError` | CLI 基础异常（含 exit_code） |
| `ConfigError` | 配置相关异常 |
| `AuthError` | 认证相关异常 |
| `ToolError` | 工具执行异常 |
| `PermissionError` | 权限相关异常 |
| `NetworkError` | 网络相关异常 |
| `ValidationError` | 输入校验异常 |
| `is_user_facing_error()` | 判断错误是否应展示给用户 |
| `format_error_for_display()` | 格式化错误供显示 |

### JSON 工具 (json)

| 函数 | 说明 |
|------|------|
| `json_parse()` | 带更好错误提示的 JSON 解析 |
| `json_stringify()` | JSON 序列化 |
| `safe_json_parse()` | 解析失败返回默认值的 JSON 解析 |
| `is_json_string()` | 检查字符串是否为有效 JSON |
| `normalize_json_key()` | 标准化 JSON 配置键 |

### 路径工具 (path)

| 函数 | 说明 |
|------|------|
| `normalize_path()` | 规范化路径为 Path 对象 |
| `is_absolute_path()` | 判断是否为绝对路径 |
| `join_paths()` | 连接路径组件 |
| `get_home_dir()` | 获取用户主目录 |
| `get_config_home()` | 获取平台配置目录 |
| `get_cache_dir()` | 获取平台缓存目录 |
| `ensure_dir_exists()` | 确保目录存在 |
| `is_subpath()` | 判断是否为子路径 |
| `windows_to_posix_path()` | Windows 路径转 POSIX 格式 |
| `posix_to_windows_path()` | POSIX 路径转 Windows 格式 |
| `get_relative_path()` | 获取相对路径 |
| `path_to_uri()` | 路径转 file:// URI |
| `uri_to_path()` | file:// URI 转路径 |

### 环境工具 (env)

| 函数/类 | 说明 |
|---------|------|
| `EnvInfo` | 环境信息 dataclass |
| `get_env_info()` | 获取完整环境信息 |
| `is_ci()` | 检测 CI 环境 |
| `is_test()` | 检测测试模式 |
| `is_production()` | 检测生产模式 |
| `is_development()` | 检测开发模式 |
| `get_env_bool()` | 获取布尔类型环境变量 |
| `get_env_int()` | 获取整数类型环境变量 |
| `get_env_str()` | 获取字符串环境变量 |
| `is_env_truthy()` | 检查环境变量是否为真值 |
| `get_required_env()` | 获取必选环境变量 |
| `get_claude_config_dir()` | 获取 Claude 配置目录 |
| `get_claude_data_dir()` | 获取 Claude 数据目录 |

### 认证工具 (auth)

| 函数/类 | 说明 |
|---------|------|
| `ApiKeySource` | API Key 来源枚举 |
| `ApiKeyResult` | API Key 查询结果 dataclass |
| `OAuthTokens` | OAuth token dataclass |
| `is_bare_mode()` | 检测 --bare 模式 |
| `is_anthropic_auth_enabled()` | 检测是否启用 Anthropic 认证 |
| `has_anthropic_api_key_auth()` | 检测是否有 API Key 认证 |
| `get_anthropic_api_key()` | 获取 API Key |
| `get_anthropic_api_key_with_source()` | 获取 API Key 及其来源 |
| `get_auth_token_source()` | 获取认证 token 来源 |
| `is_claude_ai_subscriber()` | 检测是否为 Claude.ai 订阅用户 |
| `get_subscription_type()` | 获取订阅类型 (max/pro/team/enterprise) |
| `is_max_subscriber()` | 检测 Max 订阅 |
| `is_pro_subscriber()` | 检测 Pro 订阅 |
| `is_team_subscriber()` | 检测 Team 订阅 |
| `is_enterprise_subscriber()` | 检测 Enterprise 订阅 |
| `get_subscription_name()` | 获取订阅名称 |
| `has_opus_access()` | 检测 Opus 模型访问权限 |
| `get_claude_ai_oauth_tokens()` | 获取 OAuth tokens |
| `is_oauth_token_expired()` | 检测 token 是否过期 |
| `clear_oauth_token_cache()` | 清除 token 缓存 |
| `get_api_key_from_api_key_helper()` | 执行 apiKeyHelper 获取 Key |
| `clear_api_key_helper_cache()` | 清除 apiKeyHelper 缓存 |
| `is_running_on_homespace()` | 检测是否运行在 Homespace |

### API 工具 (api)

| 函数/类 | 说明 |
|---------|------|
| `ToolSchemaCache` | Tool schema 缓存类 |
| `get_tool_schema_cache()` | 获取全局 tool schema 缓存 |
| `tool_to_api_schema()` | 转换 tool 为 API schema 格式 |
| `SystemPromptBlock` | System prompt 块 dataclass |
| `split_sys_prompt_prefix()` | 分割 system prompt 用于缓存控制 |
| `append_system_context()` | 追加系统上下文到 prompt |
| `prepend_user_context()` | 前置用户上下文到消息 |
| `normalize_tool_input()` | 规范化 tool 输入参数 |
| `normalize_tool_input_for_api()` | 剥离 API 不需要的字段 |
| `ContextMetrics` | Context 指标 dataclass |
| `calculate_context_metrics()` | 计算 context 指标 |

### 日志工具 (log)

| 函数/类 | 说明 |
|---------|------|
| `ErrorLogSink` | 错误日志 sink 接口 |
| `log_error()` | 记录错误到多端 |
| `get_in_memory_errors()` | 获取内存错误队列 |
| `log_mcp_error()` | 记录 MCP 错误 |
| `log_mcp_debug()` | 记录 MCP 调试信息 |
| `attach_error_log_sink()` | 附加错误日志 sink |
| `load_error_logs_from_dir()` | 从目录加载错误日志 |
| `date_to_filename()` | 日期转文件名格式 |

### 调试工具 (debug)

| 函数/类 | 说明 |
|---------|------|
| `is_debug_mode()` | 检测调试模式 |
| `enable_debug_logging()` | 启用调试日志 |
| `is_debug_to_stderr()` | 检测是否输出到 stderr |
| `get_debug_file_path()` | 获取 debug 文件路径 |
| `set_has_formatted_output()` | 标记有格式化输出 |
| `get_debug_log_path()` | 获取 debug 日志路径 |
| `log_for_debugging()` | 记录调试日志（分级） |
| `flush_debug_logs()` | 刷新调试日志到磁盘 |
| `log_ant_error()` | 记录 ant 用户专属错误 |
| `DebugLogWriter` | 缓冲写入 writer 类 |

### 统计工具 (stats)

| 函数/类 | 说明 |
|---------|------|
| `DailyActivity` | 单日活动 dataclass |
| `DailyModelTokens` | 单日模型 token dataclass |
| `StreakInfo` | 连击信息 dataclass |
| `SessionStats` | Session 统计 dataclass |
| `ClaudeCodeStats` | 聚合统计 dataclass |
| `to_date_string()` | datetime 转 YYYY-MM-DD |
| `get_today_date_string()` | 获取今日日期字符串 |
| `get_yesterday_date_string()` | 获取昨日日期字符串 |
| `is_date_before()` | 比较两个日期字符串 |
| `calculate_streaks()` | 计算连击信息 |
| `process_session_files()` | 处理 session 文件 |
| `aggregate_claude_code_stats()` | 聚合所有 session 统计 |

### 会话状态工具 (session_state)

| 函数/类 | 说明 |
|---------|------|
| `SessionState` | 会话状态枚举 (idle/running/requires_action) |
| `RequiresActionDetails` | 需要操作详情 dataclass |
| `SessionExternalMetadata` | 外部元数据 dataclass |
| `get_session_state()` | 获取当前会话状态 |
| `notify_session_state_changed()` | 通知会话状态变更 |
| `notify_session_metadata_changed()` | 通知元数据变更 |
| `notify_permission_mode_changed()` | 通知权限模式变更 |
| `set_session_state_changed_listener()` | 设置状态变更监听器 |
| `set_session_metadata_changed_listener()` | 设置元数据变更监听器 |
| `set_permission_mode_changed_listener()` | 设置权限模式变更监听器 |

### 附件工具 (attachments)

| 函数/类 | 说明 |
|---------|------|
| `PastedContent` | 粘贴内容 dataclass (文本/图片) |
| `ImageDimensions` | 图片尺寸 dataclass |
| `HistoryEntry` | 历史记录条目 |
| `CONTENT_TYPE_TEXT` | 常量 "text" |
| `CONTENT_TYPE_IMAGE` | 常量 "image" |
| `FileTooLargeError` | 文件超过大小限制异常 |
| `MaxTokenExceededError` | 内容超过 token 限制异常 |
| `count_tokens()` | 估算文本 token 数 |
| `is_valid_image_type()` | 检查是否为有效图片类型 |
| `get_image_dimensions()` | 获取图片尺寸 |
| `resize_image_if_needed()` | 按需缩放图片 |
| `encode_image_base64()` | 图片 base64 编码 |
| `get_file_size_mb()` | 获取文件大小(MB) |
| `validate_file_size()` | 验证文件大小限制 |
| `create_pasted_content()` | 创建粘贴内容 |
| `get_pasted_content()` | 获取粘贴内容 |
| `get_image_paste_ids()` | 从文本提取图片粘贴ID |
| `is_valid_image_paste()` | 验证图片粘贴引用 |

### Cron 工具 (cron)

| 函数/类 | 说明 |
|---------|------|
| `CronFields` | 解析后的 cron 字段 dataclass |
| `parse_cron_expression()` | 解析 5 段 cron 表达式 |
| `compute_next_cron_run()` | 计算下次执行时间 |
| `cron_to_human()` | Cron 转人类可读字符串 |

### 清理工具 (cleanup)

| 函数/类 | 说明 |
|---------|------|
| `CleanupResult` | 清理结果 dataclass |
| `cleanup_old_files_in_directory()` | 清理目录中的旧文件 |
| `cleanup_old_message_files()` | 清理旧消息/错误日志 |
| `cleanup_old_session_files()` | 清理旧 session 文件 |
| `cleanup_old_plan_files()` | 清理旧 plan 文件 |
| `cleanup_old_debug_logs()` | 清理旧 debug 日志 |
| `cleanup_old_session_env_dirs()` | 清理旧 session-env 目录 |
| `cleanup_old_file_history_backups()` | 清理旧文件历史备份 |
| `cleanup_old_message_files_in_background()` | 后台运行所有清理 |

### Shell 工具 (bash/)

| 函数/类 | 说明 |
|---------|------|
| `quote()` | 引用 shell 参数列表 |
| `quote_single()` | 引用单个 shell 参数 |
| `try_parse_shell_command()` | 解析 shell 命令为 token |
| `ParseResult` | 解析结果 dataclass |
| `get_shell_completions()` | 获取 shell 补全建议 |
| `parse_input_context()` | 解析补全上下文 |
| `get_shell_type()` | 检测当前 shell 类型 |

### 建议工具 (suggestions/)

| 函数/类 | 说明 |
|---------|------|
| `find_mid_input_slash_command()` | 查找输入中部的 slash 命令 |
| `get_best_command_match()` | 获取最佳命令匹配 |
| `is_command_input()` | 检测是否为命令输入 |
| `has_command_args()` | 检测命令是否有参数 |
| `format_command()` | 格式化命令字符串 |
| `generate_command_suggestions()` | 生成命令建议 |
| `apply_command_suggestion()` | 应用选择的建议 |
| `find_slash_command_positions()` | 查找所有 slash 命令位置 |
| `get_shell_history_suggestions()` | 从 shell 历史获取补全 |
| `get_directory_completions()` | 获取目录/文件路径补全 |

### 代码索引工具 (code_indexing)

| 函数/类 | 说明 |
|---------|------|
| `CodeIndexingTool` | 代码索引工具类型字面量 |
| `detect_code_indexing_from_command()` | 从 CLI 命令检测代码索引工具 |
| `detect_code_indexing_from_mcp_tool()` | 从 MCP 工具名检测代码索引工具 |
| `detect_code_indexing_from_mcp_server_name()` | 从 MCP 服务器名检测代码索引工具 |

### 桌面深度链接工具 (desktop_deep_link)

| 函数/类 | 说明 |
|---------|------|
| `build_desktop_deep_link()` | 构建 Claude Desktop 深度链接 URL |
| `is_desktop_installed()` | 检查 Claude Desktop 是否已安装 |
| `get_desktop_version()` | 获取已安装的 Claude Desktop 版本 |
| `get_desktop_install_status()` | 获取完整的安装状态（含版本检查） |
| `open_current_session_in_desktop()` | 打开当前会话的深度链接 |

### 终端录像工具 (asciicast)

| 函数/类 | 说明 |
|---------|------|
| `get_record_file_path()` | 获取 asciicast 录像文件路径 |
| `get_session_recording_paths()` | 获取当前会话的所有录像文件路径 |
| `flush_asciicast_recorder()` | 刷新录像数据到磁盘 |
| `install_asciicast_recorder()` | 安装 asciicast 录像器 |
| `_reset_recording_state_for_testing()` | 重置录像状态（测试用） |

### 对话恢复工具 (conversation_recovery)

| 函数/类 | 说明 |
|---------|------|
| `TurnInterruptionState` | Turn 中断状态 dataclass |
| `DeserializeResult` | 反序列化结果 dataclass |
| `migrate_legacy_attachment_types()` | 迁移旧版附件类型 |
| `deserialize_messages()` | 反序列化消息用于恢复 |
| `deserialize_messages_with_interrupt_detection()` | 反序列化并检测中断状态 |

### 提交归属工具 (commit_attribution)

| 函数/类 | 说明 |
|---------|------|
| `INTERNAL_MODEL_REPOS` | 内部模型仓库域名集合 |
| `get_attribution_repo_root()` | 获取归属操作使用的仓库根目录 |
| `get_repo_class_cached()` | 获取缓存的仓库分类结果 |
| `is_internal_model_repo_cached()` | 检查缓存的内部模型仓库状态 |
| `is_internal_model_repo()` | 检查当前仓库是否允许内部模型名 |
| `sanitize_model_name()` | 将内部模型名转为公开名称 |
| `sanitize_surface_key()` | 将 surface key 转为公开模型名 |
| `reset_repo_class_cache()` | 重置仓库分类缓存 |

### 光标/杀环工具 (cursor)

| 函数/类 | 说明 |
|---------|------|
| `KILL_RING_MAX_SIZE` | 常量，杀环最大容量 (10) |
| `push_to_kill_ring()` | 添加文本到杀环 |
| `get_last_kill()` | 获取最近杀的文本 |
| `get_kill_ring_item()` | 按索引获取杀环项 |
| `get_kill_ring_size()` | 获取杀环大小 |
| `clear_kill_ring()` | 清空杀环 |
| `reset_kill_accumulation()` | 重置杀累积标志 |
| `record_yank()` | 记录yank位置用于yank-pop |
| `can_yank_pop()` | 检查是否可以yank-pop |
| `yank_pop()` | 执行yank-pop操作 |
| `update_yank_length()` | 更新记录的yank长度 |
| `reset_yank_state()` | 重置yank状态 |
| `get_yank_position()` | 获取yank位置 |

### UUID 工具 (uuid)

| 函数 | 说明 |
|------|------|
| `validate_uuid()` | 验证是否为有效 UUID 字符串 |
| `create_agent_id()` | 生成带前缀的 agent ID（a{label-}{16hex}） |

### 临时文件工具 (tempfile)

| 函数 | 说明 |
|------|------|
| `generate_temp_file_path()` | 生成临时文件路径（支持内容哈希稳定路径） |

### XML 工具 (xml)

| 函数 | 说明 |
|------|------|
| `escape_xml()` | 转义 XML 文本内容中的特殊字符（&、<、>） |
| `escape_xml_attr()` | 转义 XML 属性值中的特殊字符（含引号） |

### YAML 工具 (yaml)

| 函数 | 说明 |
|------|------|
| `parse_yaml()` | 安全解析 YAML 字符串为 Python 对象（safe_load） |

## 变更记录 (Changelog)

- 2026-04-14：新增 xml.py 和 yaml.py，实现 XML 转义与 YAML 解析工具
- 2026-04-14：新增 uuid.py 和 tempfile.py，实现 UUID 验证/agent ID 生成与临时文件路径工具

- 2026-04-14：新增 cursor.py，实现 Emacs 风格杀环管理（yank-pop 支持）
- 2026-04-14：新增 commit_attribution.py，实现提交归属工具（模型名规范化、仓库分类）
- 2026-04-14：新增 code_indexing.py、desktop_deep_link.py、asciicast.py、conversation_recovery.py，实现 P1 Utils 剩余四个工具
- 2026-04-14：新增 attachments.py，实现消息附件处理（文本/图片粘贴、尺寸、token估算）
- 2026-04-14：新增 U1-U10 Utils 实现 — auth、api、log、debug、stats、session_state、cron、cleanup、bash/、suggestions/
- 2026-04-13：新增 `utils/` 模块，实现 errors、json、path、env 四个工具子模块
