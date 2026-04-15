[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **swarm**

# swarm

## 模块职责

`py_claw/swarm/` 是 Python 版的多智能体团队编排模块，基于 `ClaudeCode-main/src/utils/swarm/`。负责：

- 团队文件管理与成员生命周期
- tmux/iTerm2 pane 管理
- Git worktree 管理
- 会话清理
- 进程内队友执行与上下文隔离
- 队友间权限同步

## 入口与启动

- 主入口：`py_claw.swarm`
- 团队帮助函数：`py_claw.swarm.team_helpers`
- 类型定义：`py_claw.swarm.types`

## 对外接口

### 常量

- `TEAM_LEAD_NAME` - 团队领导名称
- `SWARM_SESSION_NAME` - Swarm 会话名称
- `SWARM_VIEW_WINDOW_NAME` - Swarm 视图窗口名称
- `TMUX_COMMAND` - tmux 命令
- `HIDDEN_SESSION_NAME` - 隐藏会话名称
- `TEAMMATE_COMMAND_ENV_VAR` - 队友命令环境变量
- `TEAMMATE_COLOR_ENV_VAR` - 队友颜色环境变量
- `PLAN_MODE_REQUIRED_ENV_VAR` - 需要计划模式环境变量

### 函数

- `get_swarm_socket_name()` - 获取 Swarm socket 名称（含 PID）

## 核心模块

| 模块 | 路径 | 职责 |
|------|------|------|
| spawn_utils | `swarm/spawn_utils.py` | 队友进程生成工具函数 |
| leader_permission_bridge | `swarm/leader_permission_bridge.py` | Leader 权限队列桥接 |
| permission_sync | `swarm/permission_sync.py` | 队友间权限同步 |
| reconnection | `swarm/reconnection.py` | 队友重连上下文初始化 |
| in_process_runner | `swarm/in_process_runner.py` | 进程内队友执行器 |
| teammate_init | `swarm/teammate_init.py` | 队友 Hook 初始化 |
| teammate_layout_manager | `swarm/teammate_layout_manager.py` | 队友面板布局管理 |
| teammate_model | `swarm/teammate_model.py` | 队友模型选择 |
| teammate_prompt_addendum | `swarm/teammate_prompt_addendum.py` | 队友系统提示词补充 |

## Backends 子模块

| 模块 | 路径 | 职责 |
|------|------|------|
| detection | `backends/detection.py` | tmux/iTerm2 检测 |
| InProcessBackend | `backends/in_process_backend.py` | 进程内队友执行后端 |
| it2_setup | `backends/it2_setup.py` | iTerm2 it2 CLI 安装与验证 |
| ITermBackend | `backends/iterm_backend.py` | iTerm2 split pane 后端 |
| pane_backend_executor | `backends/pane_backend_executor.py` | PaneBackend → TeammateExecutor 适配器 |
| teammate_mode_snapshot | `backends/teammate_mode_snapshot.py` | 队友模式快照 |

## 数据模型

- `TeamFile` - 团队配置文件结构
- `TeamMember` - 团队成员
- `TeamAllowedPath` - 团队允许路径
- `BackendType` - 后端类型（tmux/iTerm2/in_process/web）
- `SessionStatus` - 会话状态
- `SpawnTeamInput/Output` - spawn team 输入输出
- `CleanupOutput` - 清理输出
- `SwarmPermissionRequest` - 队友权限请求
- `PermissionResolution` - 权限决议

## 关键依赖与配置

- 依赖 `py_claw.settings` 用于团队目录配置
- 使用 `~/.claude/teams/` 作为默认团队目录

## 测试与质量

- 进程内队友执行器 (in_process_runner)
- 权限同步系统 (permission_sync)
- 后端检测与选择 (detection, registry)

## 相关文件清单

- `__init__.py` - 模块入口与常量
- `types.py` - 类型定义
- `team_helpers.py` - 团队文件操作
- `spawn_utils.py` - 队友生成工具
- `leader_permission_bridge.py` - Leader 权限桥接
- `permission_sync.py` - 权限同步
- `reconnection.py` - 重连上下文
- `in_process_runner.py` - 进程内执行器
- `teammate_init.py` - 队友初始化
- `teammate_layout_manager.py` - 布局管理
- `teammate_model.py` - 模型选择
- `teammate_prompt_addendum.py` - 提示词补充
- `backends/` - 后端实现
  - `types.py` - 后端类型协议
  - `registry.py` - 后端注册
  - `tmux_backend.py` - TmuxBackend
  - `detection.py` - 环境检测
  - `in_process_backend.py` - 进程内后端
  - `it2_setup.py` - it2 安装
  - `iterm_backend.py` - iTerm2 后端
  - `pane_backend_executor.py` - 适配器
  - `teammate_mode_snapshot.py` - 模式快照

## 变更记录 (Changelog)

- 2026-04-14：完成 W1-W16 Swarm 全部 16 个核心模块实现
  - 新增 spawn_utils、leader_permission_bridge、permission_sync、reconnection
  - 新增 in_process_runner、teammate_init、teammate_layout_manager、teammate_model、teammate_prompt_addendum
  - 新增 detection、InProcessBackend、it2Setup、ITermBackend、PaneBackendExecutor、teammateModeSnapshot
- 2026-04-13：新增 swarm 模块，实现基础常量、类型定义和团队文件操作
- 2026-04-13：新增 backends/ 子模块，实现后端类型定义、注册表和 TmuxBackend
