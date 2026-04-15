# context service

> **状态**: ✅ 已完成
> **TS 参考**: `ClaudeCode-main/src/context.ts`

## 模块职责

`context` 服务提供系统上下文和用户上下文的加载与格式化，用于在每次对话开始时注入到 prompt 中：

- **系统上下文** (`get_system_context`)：Git 仓库状态（branch、main branch、status、recent commits、git user）
- **用户上下文** (`get_user_context`)：从多个位置加载的 `CLAUDE.md` 内容 + 当前日期

核心功能与 TS 参考树 `src/context.ts` 中的 `getSystemContext()` 和 `getUserContext()` 对齐。

## 关键文件

| 文件 | 职责 |
|------|------|
| `service.py` | 核心实现：Git 状态获取、Claude.md 发现与加载、上下文缓存 |
| `types.py` | `GitStatus`、`SystemContext`、`UserContext`、`ContextResult` 数据类 |
| `config.py` | `ContextConfig` 配置（环境变量开关、最大字符数限制） |
| `__init__.py` | 公开 API 聚合 |

## 公开 API

```python
from py_claw.services.context import (
    get_context,
    get_system_context,
    get_user_context,
    get_git_status,
    get_claude_md_content,
    get_context_config,
    clear_context_cache,
)
```

### get_git_status(cwd=None)

返回格式化的 Git 状态字符串（已缓存，进程级）。

**返回值示例**：
```
This is the git status at the start of the conversation. Note that this status is a snapshot in time, and will not update during the conversation.

Current branch: feature-xyz
Main branch (you will usually use this for PRs): main
Git user: cacaview
Status:
 M src/foo.py
?? tests/

Recent commits:
e803624 chore: initialize repository
```

### get_claude_md_content(cwd=None)

从多个位置按优先级加载并合并 `CLAUDE.md` 内容（已缓存，进程级）。

**加载顺序（低→高优先级）**：
1. `/etc/claude-code/CLAUDE.md`（仅 Unix，全局托管规则）
2. `~/.claude/CLAUDE.md`（用户级）
3. 从当前目录向上遍历找到的 `CLAUDE.md`、`.claude/CLAUDE.md`、`.claude/rules/*.md`（项目级）

### get_system_context(include_git=True, cache_breaker=None)

返回 `SystemContext` 对象，包含 `git_status` 和 `cache_breaker` 字段。

### get_user_context()

返回 `UserContext` 对象，包含 `claude_md` 和 `current_date` 字段。

### get_context()

返回 `ContextResult(system=<SystemContext>, user=<UserContext>)`，一次性获取组合上下文。

## 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `include_git_status` | `True` | 是否包含 Git 状态 |
| `include_claude_md` | `True` | 是否加载 CLAUDE.md |
| `max_status_chars` | `2000` | Git status 截断阈值 |
| `max_memory_chars` | `40000` | CLAUDE.md 总长度上限 |

**环境变量**：
- `CLAUDE_CODE_REMOTE`：禁用 Git 状态获取
- `CLAUDE_CODE_DISABLE_CLAUDE_MDS`：禁用 CLAUDE.md 加载

## 已知限制

- Claude.md 的 `@include` 指令解析尚未实现（TS 版本支持 `@path` 语法）
- 尚未接入 `analytics` 服务的诊断日志（TS 版本有 `logForDiagnosticsNoPII` 调用）
- 尚未实现 `setCachedClaudeMdContent` 供 auto-mode classifier 使用

## 变更记录

- 2026-04-13：实现 M4 context 服务，对齐 TS `src/context.ts`
