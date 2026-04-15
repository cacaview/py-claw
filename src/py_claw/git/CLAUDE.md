# git

## 模块职责

`git/` 模块提供 Git 操作、解析和类型定义，用于 py-claw 运行时的 Git 状态管理和差异计算。相当于 TypeScript 参考树中的 `ClaudeCode-main/src/utils/git.ts`。

## 子模块导航

- `types.py` — Git 类型定义（GitDiffStats、PerFileStats、GitRepoState 等）
- `parsers.py` — Git 输出解析器（parse_shortstat、parse_git_numstat 等）
- `operations.py` — Git 操作函数（find_git_root、get_git_state 等）

## 关键功能

### 类型定义 (`types.py`)
- `GitDiffStats` — 差异统计摘要
- `PerFileStats` — 单文件差异统计
- `StructuredPatchHunk` — 统一补丁的 hunk 结构
- `GitDiffResult` — 完整差异结果
- `GitRepoState` — Git 仓库状态快照
- `PreservedGitState` — Issue 提交的持久化状态
- `BINARY_EXTENSIONS` — 二进制文件扩展名集合

### 解析器 (`parsers.py`)
- `parse_shortstat()` — 解析 `git diff --shortstat` 输出
- `parse_git_numstat()` — 解析 `git diff --numstat` 输出
- `parse_git_diff_hunks()` — 解析统一 diff 为 per-file hunks
- `parse_diff_line()` — 解析单行 diff 输出
- `is_binary_file_extension()` — 检查文件是否为二进制扩展名

### 操作函数 (`operations.py`)
- `find_git_root()` — 向上遍历目录树查找 .git
- `get_git_state()` — 返回完整仓库状态快照
- `fetch_git_diff()` — 获取工作树与 HEAD 的差异统计
- `fetch_git_diff_hunks()` — 按需获取差异 hunks
- `stash_to_clean_state()` — 暂存所有更改
- `get_changed_files()` — 获取已更改文件列表
- `get_file_status()` — 获取文件状态（tracked/untracked）
- `get_head()` / `get_branch()` / `get_remote_url()` — 获取仓库信息
- `get_is_clean()` — 检查工作树是否干净
- `preserve_git_state_for_issue()` — 为 issue 提交保留 Git 状态

## 常量

- `GIT_TIMEOUT_MS` — Git 命令超时（5 秒）
- `MAX_FILES` — 最大文件数（50）
- `MAX_DIFF_SIZE_BYTES` — 最大差异大小（1MB）
- `MAX_LINES_PER_FILE` — 每文件最大行数（400）
- `MAX_FILES_FOR_DETAILS` — 超过此数量则跳过详情（500）

## 基于 ClaudeCode-main/src/utils/git.ts

此模块参考上游 TypeScript 实现，功能对齐包括：
- 暂存状态检测（merge/rebase/cherry-pick/revert）
- 二进制文件处理
- shallow clone 处理
- worktree 支持
- 远程 base 查找与规范化
- Issue 提交的 Git 状态持久化
