[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > [services](../services/CLAUDE.md) > **commit**

# commit

## 模块职责

`commit/` 提供 Git commit 分析和 preparation 服务，包含：

- **Attribution tracking**：跟踪 Claude 对文件的字符级贡献
- **Staged change analysis**：分析暂存区的文件变更
- **Commit prompt generation**：生成符合 Git Safety Protocol 的 commit prompt

Reference: ClaudeCode-main/src/commands/commit.ts
          ClaudeCode-main/src/utils/commitAttribution.ts

## 子模块导航

- `types.py` — AttributionState、FileAttributionState、CommitAnalysisResult 等数据模型
- `service.py` — Git 操作、attribution 计算、prompt 生成的核心实现

## 核心类型

### AttributionState
跟踪 Claude 在整个会话期间对文件的贡献：
- `file_states: dict[str, FileAttributionState]` — 按文件路径存储的贡献状态
- `session_baselines: dict[str, ContentBaseline]` — 会话基线
- `prompt_count` / `permission_prompt_count` / `escape_count` — 各类计数

### FileAttributionState
单个文件的 attribution 状态：
- `content_hash: str` — 文件内容哈希
- `claude_contribution: int` — Claude 贡献的字符数
- `mtime: float` — 修改时间

### CommitAnalysisResult
暂存区分析结果：
- `staged_files`, `modified_files`, `new_files`, `deleted_files` — 分类文件列表
- `has_staged_changes: bool` — 是否有暂存变更
- `current_branch: str` — 当前分支
- `recent_commits: list[str]` — 最近提交
- `is_in_transient_state: bool` — 是否处于 rebase/merge 等 transient 状态

### CommitPreparationResult
Commit 准备结果：
- `ready: bool` — 是否可以提交
- `error_message: str | None` — 不可提交时的错误信息
- `attribution_data: AttributionData | None` — Attribution 数据

## 公开 API

```python
from py_claw.services.commit import (
    # 状态管理
    create_empty_attribution_state,
    track_file_modification,
    # Git 操作
    get_staged_files,
    get_git_status,
    get_git_diff,
    get_current_branch,
    get_recent_commits,
    # 分析与准备
    analyze_staged_changes,
    prepare_commit,
    build_commit_prompt,
)
```

## 内部模型白名单

`_INTERNAL_MODEL_REPOS` 列表允许特定内部仓库在 commit trailer 中使用内部模型名称。

## 模型名称清洗

`_MODEL_SANITIZATION` 将内部模型名称（如 `opus-4-6`）映射到公开名称（如 `claude-opus-4-6`）。

## Git Safety Protocol

`build_commit_prompt()` 生成的 prompt 包含以下安全规则：

- NEVER update the git config
- NEVER skip hooks (--no-verify, --no-gpg-sign) unless explicitly requested
- CRITICAL: ALWAYS create NEW commits, NEVER amend unless explicitly requested
- Do not commit secrets (.env, credentials.json)
- Never use git commands with -i flag

## 变更记录 (Changelog)

- 2026-04-13：新增 `commit/` 模块，实现 M10 功能（Git commit 分析和 preparation）
