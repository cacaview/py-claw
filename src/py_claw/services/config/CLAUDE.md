[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > [services](../CLAUDE.md) > **config**

# config

## 模块职责

`config` 服务提供全局配置和项目级配置的管理，对应 TypeScript 参考树 `ClaudeCode-main/src/utils/config.ts` 的核心功能：

- 全局配置（`~/.claude/settings.json`）读写，带内存缓存和写穿透
- 项目级配置存储在全局配置的 `projects` 字段下，按 git root 路径为 key
- Auth 状态防丢失保护（oauthAccount、hasCompletedOnboarding）
- 配置备份与损坏恢复（备份到 `~/.claude/backups/`）
- 信任对话框接受状态跨父目录继承检查

## 入口与启动

- 主入口：`service.py::get_global_config`、`service.py::save_global_config`
- 类型定义：`types.py::GlobalConfig`、`types.py::ProjectConfig`

## 对外接口

### 核心函数

- `get_global_config() -> GlobalConfig`：获取全局配置（带缓存）
- `save_global_config(updater) -> None`：保存全局配置，updater 接收当前配置返回新配置
- `get_current_project_config(cwd?) -> ProjectConfig`：获取当前项目配置
- `save_current_project_config(updater, cwd?) -> None`：保存当前项目配置
- `get_project_path_for_config(cwd?) -> str`：获取项目路径（git root 或 cwd）

### 便捷函数

- `get_theme() -> str`：获取主题设置
- `set_theme(theme: str) -> None`：设置主题
- `is_auto_compact_enabled() -> bool`：检查自动压缩是否启用
- `increment_startup_count() -> None`：增加启动计数
- `get_oauth_account() -> dict | None`：获取 OAuth 账户信息
- `set_oauth_account(account: dict | None) -> None`：设置 OAuth 账户信息
- `get_or_create_user_id() -> str`：获取或创建用户 ID
- `record_first_start_time() -> None`：记录首次启动时间

## 数据模型

- `GlobalConfig`：全局配置 Pydantic 模型（100+ 字段）
- `ProjectConfig`：项目级配置 Pydantic 模型
- `GLOBAL_CONFIG_KEYS`：需要持久化的全局配置 key 列表
- `PROJECT_CONFIG_KEYS`：需要持久化的项目配置 key 列表

## 关键设计

### 配置缓存策略

- 内存缓存 `_global_config_cache` 提供快速读取路径
- 写操作使用写穿透（write-through）策略
- 文件修改时间跟踪用于检测其他进程的修改

### Auth 防丢失保护

`save_global_config` 在写入前检查是否会丢失 `oauth_account` 或 `has_completed_onboarding` 状态，若会丢失则拒绝写入。

### 备份策略

- 备份存储在 `~/.claude/backups/`
- 每个配置变更最多创建一个备份，间隔 60 秒
- 保留最近 5 个备份
- 损坏的配置文件自动备份到 `~/.claude/backups/<name>.corrupted.<timestamp>`

### 信任对话框继承

信任对话框接受状态会向上检查所有父目录，如果任何父目录已接受信任，则认为当前目录也受信任。

## 关键依赖与配置

- 配置文件路径：`~/.claude/settings.json`（Windows: `%APPDATA%/.claude/settings.json`）
- 备份目录：`~/.claude/backups/`
- 依赖：`pydantic>=2.8`

## 测试

需要覆盖：
- 基本的 get/set 配置
- 项目配置的隔离（不同 git root）
- Auth 防丢失保护
- 备份创建和恢复

## 变更记录 (Changelog)

- 2026-04-13：创建 config 服务模块，实现 M3 功能（config service）
