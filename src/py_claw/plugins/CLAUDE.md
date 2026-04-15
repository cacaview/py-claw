# plugins

## 模块职责

`py_claw/plugins/` 是 Python 版 Claude Code 的插件系统实现，对标 TypeScript 参考树的 `ClaudeCode-main/src/plugins/`。

提供：
- 内置插件注册表
- 插件清单 (plugin.json) 加载和验证
- 插件启用/禁用管理
- 插件安装作用域 (user/project/local/managed)
- installed_plugins.json 管理

## 入口与启动

- 模块入口: `__init__.py`
- 内置插件初始化: `builtin.py::init_builtin_plugins()`
- 插件注册表: `registry.py::get_plugin_registry()`

## 对外接口

### 内置插件 (builtin.py)

| 函数/类 | 说明 |
|---------|------|
| `BUILTIN_MARKETPLACE_NAME` | 常量 "builtin" |
| `BUILTIN_PLUGINS` | 内置插件注册表 |
| `BuiltinPluginDefinition` | 内置插件定义 dataclass |
| `register_builtin_plugin()` | 注册内置插件 |
| `is_builtin_plugin_id()` | 检查是否为内置插件 ID |
| `get_builtin_plugin_definition()` | 获取内置插件定义 |
| `get_builtin_plugins()` | 获取所有内置插件 |
| `get_builtin_plugin_skill_commands()` | 获取内置插件技能命令 |
| `clear_builtin_plugins()` | 清除内置插件 (测试用) |
| `init_builtin_plugins()` | 初始化内置插件 |

### 类型 (types.py)

| 类 | 说明 |
|----|------|
| `PluginScope` | 插件安装作用域枚举 (managed/user/project/local) |
| `PluginAuthor` | 插件作者信息 |
| `DependencyRef` | 插件依赖引用 |
| `CommandPath` | 命令路径 |
| `CommandMetadata` | 命令元数据 |
| `McpServerConfig` | MCP 服务器配置 |
| `LspServerConfig` | LSP 服务器配置 |
| `ChannelDeclaration` | MCP 通道声明 |
| `HookConfig` | Hook 配置 |
| `SkillPath` | 技能路径 |
| `AgentPath` | Agent 路径 |
| `StylePath` | 输出样式路径 |
| `PluginManifest` | 插件清单 (对应 TS PluginManifest) |
| `PluginSource` | 插件源规范 |
| `PluginMarketplaceEntry` | 市场插件条目 |
| `LoadedPlugin` | 已加载插件运行时状态 |
| `PluginInstallationEntry` | 插件安装条目 |
| `InstalledPluginsFileV2` | installed_plugins.json V2 格式 |
| `PluginError` | 插件错误基类 |
| `PluginNotFoundError` | 插件未找到错误 |
| `PluginLoadError` | 插件加载错误 |
| `PluginDependencyError` | 插件依赖错误 |
| `PluginValidationError` | 插件验证错误 |

### 清单 (manifest.py)

| 函数 | 说明 |
|------|------|
| `validate_plugin_manifest()` | 验证插件清单 |
| `load_plugin_manifest()` | 从目录加载插件清单 |
| `save_plugin_manifest()` | 保存插件清单到目录 |
| `load_installed_plugins()` | 加载 installed_plugins.json |
| `save_installed_plugins()` | 保存 installed_plugins.json |

### 注册表 (registry.py)

| 函数/类 | 说明 |
|---------|------|
| `PluginRegistry` | 插件注册表类 |
| `get_plugin_registry()` | 获取全局插件注册表实例 |
| `is_plugin_enabled()` | 检查插件是否启用 |
| `enable_plugin()` | 启用插件 |
| `disable_plugin()` | 禁用插件 |
| `get_plugin_scope()` | 获取插件安装作用域 |
| `get_installed_plugins()` | 获取所有已安装插件 |
| `add_installed_plugin()` | 添加已安装插件 |
| `remove_installed_plugin()` | 移除已安装插件 |
| `get_plugin_config()` | 获取插件配置 |
| `set_plugin_config()` | 设置插件配置 |

## 关键依赖与配置

- 插件配置存储在 `~/.claude/settings.json` (enabledPlugins, pluginConfigs)
- 插件安装元数据存储在 `~/.claude/installed_plugins.json`
- 插件 ID 格式: `{name}@{marketplace}` (如 `code-formatter@builtin`)

## 数据模型

核心数据结构:
- `PluginManifest` - plugin.json 内容结构
- `LoadedPlugin` - 运行时已加载插件状态
- `InstalledPluginsFileV2` - 安装记录文件格式

## 测试与质量

- 尚未有自动化测试
- 待补充测试用例

## 常见问题 (FAQ)

### 插件和技能 (Skills) 有什么区别？
- 技能 (Skills) 是 .claude/skills/ 目录下的 Markdown 文件
- 插件 (Plugins) 是更完整的功能包，可以包含技能、Hook、MCP 服务器、LSP 服务器等多种组件

### 插件如何注册技能命令？
通过 `BuiltinPluginDefinition.skills` 字段定义技能，`get_builtin_plugin_skill_commands()` 会将其转换为 `CommandDefinition` 对象。

### 支持哪些插件安装作用域？
- `managed` - 企业/系统级 (只读)
- `user` - 用户全局设置
- `project` - 共享项目设置
- `local` - 个人项目覆盖

## 相关文件清单

- `__init__.py` - 模块导出
- `types.py` - 类型定义
- `builtin.py` - 内置插件注册
- `manifest.py` - 清单处理
- `registry.py` - 注册表管理

## 变更记录 (Changelog)

- 2026-04-14：新增 `plugins/` 模块，实现 plugin system (types, builtin, manifest, registry)
