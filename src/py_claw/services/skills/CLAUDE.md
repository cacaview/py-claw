[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > [services](../CLAUDE.md) > **skills**

# skills

## 模块职责

`skills` 服务是 skill 操作的统一门面，协调 skill 发现、skill 管理和 skill 搜索，提供单一入口。

对应 TypeScript 参考树：
- `ClaudeCode-main/src/services/skills/` — 当前为 stub 实现
- `ClaudeCode-main/src/skills/loadSkillsDir.ts` — 实际 skill 加载逻辑

## 入口与启动

- 主入口：`service.py::initialize_skills_service`
- 类型定义：`types.py`

## 对外接口

### 初始化

- `initialize_skills_service(cwd?, home_dir?, settings_skills?)` — 初始化 skill 服务，从标准位置加载所有 skill

### 查询

- `get_skill(name) -> SkillInfo | None` — 按名称获取 skill
- `list_skills(source?) -> list[SkillInfo]` — 列出所有 skill，可按 source 过滤
- `search_skills(query, max_results=20) -> SkillSearchResult` — 搜索 skill（名称/描述匹配 + 相关度排序）
- `get_all_skill_names() -> list[str]` — 获取所有 skill 名称
- `skill_exists(name) -> bool` — 检查 skill 是否存在

### 统计

- `get_skills_stats() -> SkillsStats` — 获取服务统计信息

### 状态管理

- `reset_skills_service()` — 重置服务状态（用于测试）

## 数据模型

- `SkillInfo` — 完整 skill 信息（含 metadata、conditional activation paths、hooks 等）
- `SkillsServiceState` — 全局服务状态
- `SkillSearchResult` — 搜索结果（含相关度评分、搜索时间）
- `SkillsStats` — 服务统计（各 source 计数、搜索统计、发现统计）

## 关键设计

### Skill Source 分类

| Source | 说明 |
|--------|------|
| `userSettings` | 用户级 `~/.claude/skills/` |
| `projectSettings` | 项目级 `.claude/skills/` |
| `builtin` | 内置 skill |
| `installed` | 已安装的 skill |
| `policy` | 策略目录 skill |
| `mcp` | MCP server 提供的 skill |

### 搜索算法

1. 精确名称匹配 → 1.0 分
2. 名称前缀匹配 → 0.8 分
3. 名称包含查询 → 0.6 分
4. 描述包含查询 → 0.4 分
5. 名称/描述词汇重叠 → 加权评分

### 与子服务的关系

- `skill_discovery/` — 动态/条件 skill 发现
- `skill_manager/` — 内置 skill 注册与执行
- `skill_search/` — 搜索与缓存

## 关键依赖与配置

- 依赖 `py_claw.skills.discover_local_skills`
- 依赖 `py_claw.services.skill_manager`
- 配置文件：无独立配置，复用子服务配置

## 测试

需要覆盖：
- 初始化加载
- 名称/描述搜索
- 过滤与排序
- 统计聚合

## 已实现的 Bundled Skills

| Skill | 说明 |
|--------|------|
| `keybindings-help` | 快捷键自定义技能 |
| `loop` | 定时任务调度技能 |
| `simplify` | 代码审查简化技能 (3 并发 Agent) |
| `skillify` | Session 转 Skill 工具 |
| `update-config` | 配置管理引导 |
| `batch` | 批处理技能 (并行工作编排) |
| `debug` | Debug 帮助技能 |
| `remember` | 记忆技能 (内存审查) |
| `stuck` | "当卡住时"技能 (进程诊断) |
| `verify` | 代码验证技能 |
| `schedule` | 远程 Agent 调度 (CCR) |
| `lorem-ipsum` | Lorem ipsum 文本生成器 |
| `dream` | 代码可视化/创意分析技能 |
| `hunter` | Bug追踪/代码质量分析技能 |
| `make-skill` | 自定义技能生成器 |
| `claude-api` | Claude API / SDK 参考技能 |
| `claudeApi` | Claude API 技能别名 |
| `claudeApi-multi` | 多语言 Claude API 参考技能 |
| `claude-in-chrome` | Claude in Chrome 集成技能 |
| `claudeInChrome` | Claude in Chrome 技能别名 |

## 变更记录 (Changelog)

- 2026-04-15：新增 7 个 bundled skills（loremIpsum、dream、hunter、runSkillGenerator、claudeApi、claude-api、claudeInChrome），总计 20 个 bundled skills 已实现
- 2026-04-13：创建 skills 服务模块，实现 M7 功能（统一 skill 管理门面）
