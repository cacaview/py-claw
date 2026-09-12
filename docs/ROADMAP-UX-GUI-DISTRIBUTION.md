# py-claw UX / GUI / 分发规划与调研

> 2026-09-12 · 基于本轮交互测试与全量修复（1903 测试全绿）之后的现状。

## 现状基线

本轮已修复的体验问题（作为规划起点）：

- TUI 权限流闭环：Allow / Always allow（会话级）/ Deny / Esc=Deny，键盘可完整操作；
- 中断真正取消回合（worker cancel + interrupt_event + 阻塞对话框解锁），无孤儿弹窗；
- 默认 system prompt（身份 + 工具指引 + 环境 + CLAUDE.md 注入），工具循环保护，
  tool_progress 带输入/输出载荷；
- 会话落盘（`~/.claude/projects/<project>/<uuid>.jsonl`），/sessions 与 /resume 可见；
- Ctrl+G 真·新会话（清 transcript + 会话级权限记忆）；
- 真流式到达 TUI（OpenAI chat chunk 实时 text_delta）；
- `--print` 模式（text/json）；api_url 归一化；模型名显示实际配置；
- Tab 接受高亮建议；Ctrl+P 不再被 Textual 命令面板劫持。

---

## 一、TUI 的进一步优化与人性化

目标：让 TUI 从"能用"到"顺手"。按投入产出排序。

### 1. 首次运行体验（onboarding）
- 无 API 配置时启动，给出内联引导（读取环境变量 `ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_BASE_URL`
  作为兜底，或交互式写入 `~/.config/py-claw/config.json`），而不是静默回到 placeholder。
- 首次进入新工作区时显示 TrustDialog（已实现但未接线）并展示当前权限模式。
- `/doctor` 面板增加连通性自检：对配置端点发一个 1-token 请求，直接给出模型连通/鉴权失败/代理拦截三种诊断。

### 2. 权限与安全的可视化
- Always allow 目前是会话级工具名粒度；下一步做 **Bash 前缀粒度**
  （如 `Bash(git *)`），并在 /permissions 面板中列出/移除本会话授权。
- 权限弹窗显示 diff 预览（Edit/Write 已有 StructuredDiff 组件，接线即可）。
- `shift+tab` 模式切换时给出一次性确认（bypass 模式进入时 toast 提示风险）。

### 3. 消息区信息密度
- 工具行增加折叠/展开（Enter 展开 tool_input/tool_response 全文），减少长输出刷屏。
- Markdown 渲染 assistant 回复（Textual 的 Markdown widget），代码块带语言高亮与复制快捷键。
- 思考/工具阶段的状态条（当前在第 N 轮工具循环、已耗时），数据已由 tool_progress 提供。

### 4. 会话与恢复
- /sessions 列表接入 FuzzyPicker（组件已有），支持模糊搜索与删除。
- Resume 后在状态栏显示"resumed from <time> · N messages"。
- /compact 接线到 services/compact，恢复长会话能力（上游对齐项）。

### 5. 快捷键一致性
- Ctrl+M（=Enter 的物理冲突）彻底从帮助/状态文案移除，Model picker 换绑
  `ctrl+o`（ iTerm2/kitty/终端普通模式均无冲突）或仅保留 `/model`。
- 引入 kitty keyboard protocol 检测（Textual 已支持），支持时恢复 Ctrl+M/Ctrl+; 等组合键。

---

## 二、GUI 版本选型

三条路线，推荐 **路线 A 起步、路线 B 为正式 GUI 形态**。

### 路线 A：`textual-serve` 浏览器版（最快见效，1-2 天）
Textualize 官方 `textual-serve` 可把现有 Textual 应用原样投到浏览器（本地或局域网）：
`pip install textual-serve` → `textual-serve --host 127.0.0.1 --port 8080 'py-claw --tui'`。
- 优点：零重构；GUI 需求（鼠标、滚动、复制、移动端局域网访问）即刻满足；与 TUI 同一套代码。
- 缺点：仍是终端观感；不能做原生菜单/托盘；多人并发需要多会话管理。
- 定位：**内部试用版/远程服务器场景**（SSH 机器上的会话直接开浏览器用）。

### 路线 B：Tauri v2 + py-claw sidecar（推荐正式形态，2-4 周）
2026 年桌面选型共识已从 Electron 转向 Tauri v2（体积 ~10MB vs 150MB+，内存约为 Electron 1/5），
且 Tauri shell plugin 内置 sidecar 进程管理。架构：

```
┌─ Tauri v2 (Rust 壳 + Web 前端 React/Svelte)
│   主窗口：会话列表 / 聊天视图 / diff 查看 / 权限卡片 / 设置
│   IPC：tauri shell plugin → py-claw --input-format stream-json --output-format stream-json
└─ py-claw（PyInstaller 打包或 uv 管理的 venv sidecar）
    复用全部现有能力：QueryRuntime / 权限引擎 / hook / 工具 / 会话落盘
```

关键设计约束：
- **GUI 不绕过协议层**：所有模型交互走 stream-json 控制协议（与 SDK/CLI 同一入口），
  权限 ask 走现有 `permission_ask_callback` → 映射为 GUI 权限卡片的三按钮。
  本轮已把 `parent_tool_use_id` 设为可选、错误信息进 `result.errors`、
  `tool_progress` 带载荷——协议面已具备喂 GUI 的信息密度。
- 会话列表直接读 `~/.claude/projects/`（与 CLI/TUI 共享）。
- 打包：macOS 用 PyInstaller 生成 sidecar 二进制（约 40-80MB），Tauri 负责壳与签名/公证。

### 路线 C：纯 Web（FastAPI + WebSocket 自建前端）
仅当需要"一个服务、多用户、远程部署"时选择。py-claw 定位是本地运行时，
自建 Web 的维护成本（鉴权、状态同步、CORS）与定位不匹配，暂不推荐。

### 不推荐
Electron（体积/内存劣势明显）；PyQt/PySide（与现有 Textual 组件无法复用，UI 需全部重写）。

---

## 三、安装、管理与使用便利性

### 1. 安装（按人群分层）
| 人群 | 命令 | 说明 |
|------|------|------|
| 有 Python 环境 | `uv tool install py-claw`（或 `pipx install`） | 隔离环境、自动管理入口 |
| 一次性试用 | `uvx --from py-claw py-claw --tui` | 免安装直接跑 |
| 非技术用户 | Tauri 安装包（.dmg/.msi/.AppImage） | 随路线 B 发布，内嵌运行时 |

工程项：
- pyproject 增加 `[project.scripts]` 之外,补 `py-claw-doctor` 入口（环境自检：Python 版本、
  端点连通、配置文件有效性、Textual 依赖）。
- 配置初始化：`py-claw init` 子命令交互式生成 `~/.config/py-claw/config.json`，
  支持从 `~/.claude/settings.json` 的 `env` 段一键导入（本机实测的 Claude Code 配置迁移路径）。

### 2. 配置管理
- `py-claw config get/set/list` 子命令，避免手编 JSON（本轮测试中 api_url 语义曾踩坑，配置面值得一等公民化）。
- 配置校验：`api_url` 归一化逻辑已有，配置时即回显最终端点。
- 代理：文档明确 httpx 尊重 `HTTP_PROXY/NO_PROXY`；`py-claw doctor` 检测系统代理并提示内网端点例外。

### 3. 会话与数据管理
- `py-claw sessions list/clean --before <date>` 子命令，管理 `~/.claude/projects` 增长。
- 更新：`py-claw version --check` 对接 PyPI（或私有源），配合 `uv tool upgrade`。

### 4. 日志与诊断
- 运行日志落 `~/.config/py-claw/logs/`（本轮测试表明：静默失败是最大排查成本，
  现在 result.errors 已带信息，日志补齐后端请求级 detail：模型、耗时、token 数）。

---

## 四、里程碑建议

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| M1（1 周） | onboarding + /doctor + config 子命令 + 会话管理命令 | 新机器 5 分钟内完成安装→对话 |
| M2（1-2 周） | textual-serve 远程版 + 权限面板 + diff 预览 + Markdown 渲染 | 局域网浏览器可用 |
| M3（2-4 周） | Tauri v2 GUI（会话列表/聊天/权限卡片/设置），PyInstaller sidecar | 三平台安装包发布 |
| M4 | /compact 接线、动态工具加载（ToolSearch）、Bash 前缀授权 | 长会话与 token 成本指标达标 |

## 参考来源

- [Tauri vs Electron 2026: 20-50x Smaller, 5x Less RAM](https://rustify.rs/articles/rust-tauri-vs-electron-2026)
- [Built a desktop OCR app on Tauri v2 with two Python sidecars](https://github.com/orgs/tauri-apps/discussions/15339)
- [Desktop Apps from Web: Tauri vs Electron vs Deno 2026](https://www.digitalapplied.com/blog/desktop-apps-web-stack-tauri-electron-deno-wails-2026)
- [Cross-Platform Desktop Wars: Electron vs Tauri](https://dev.to/nikolas_dimitroulakis_d23/cross-platform-desktop-wars-electron-vs-tauri-how-do-you-explain-the-tradeoffs-to-users-2948)
- Textual 官方 `textual-serve`（Textualize 文档 / PyPI）
