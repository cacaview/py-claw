# TODO — py-claw 工作进度

> 更新日期：2026-04-15

---

## TUI 对齐任务（按步骤拆分）

### 1. Prompt suggestion UX 收敛与对齐

1. 审计 `PromptInput` 与 `PromptFooter` 的建议展示职责，确定单一展示面
2. 删除重复建议渲染，只保留一套 slash/path/history/agent/channel 建议 UI
3. 统一建议列表的滚动窗口、选中态、分页策略与可见性规则
4. 核对并补齐 `↑↓ / PageUp / PageDown / Tab / Esc` 的行为一致性
5. 对齐空输入 `/`、部分命令、mid-input slash、path、shell history 的展示策略
6. 处理窄终端和矮终端下的建议列表退化方案
7. 补充 Prompt suggestion 交互测试或最小 smoke 脚本

### 2. REPL 主消息区升级为专用消息列表

1. 审计现有 `RichLog` 用法与仓内可复用的消息列表/虚拟列表组件
2. 确定 Python 侧主 REPL 消息区替换方案（复用现有组件或补一个专用适配层）
3. 将 `src/py_claw/ui/screens/repl.py` 从 `RichLog` 切换到结构化消息列表
4. 对齐用户/助手/系统/tool/progress 消息的样式与分组展示
5. 验证长会话下的滚动、自动定位、性能与可读性
6. 补充主消息区渲染与交互测试

### 3. 主 REPL overlay 覆盖面补齐

1. 对照 TS `REPL.tsx` 盘点已存在但未接线的 Python dialog / overlay
2. 区分必须接入主 REPL 的高优先级交互面与可后置项
3. 先补主流程相关 overlay：permission / hook prompt / MCP elicitation / exit flow
4. 再补体验增强类 overlay：idle/cost/remote/IDE onboarding/LSP-plugin recommendation 等
5. 为每个新增 overlay 补入口、关闭回路、焦点恢复与状态同步
6. 补充 overlay 交互测试与主流程 smoke test

### 4. 窄屏 / 矮屏布局策略优化

1. 盘点当前 `<80` 宽与 `<20` 高时被直接隐藏的 UI 元素
2. 重新设计窄屏降级顺序，优先压缩而不是直接隐藏关键状态信息
3. 保留最小可用的 mode / hint / suggestion / help 信息
4. 为短终端设计独立的 footer / prompt 紧凑布局
5. 手动验证 80 列以下、20 行以下的可用性与信息密度

### 5. 主交互快捷键面补齐

1. 对照 TS REPL 梳理真正影响主流程的全局快捷键与模式切换入口
2. 标记 Python 已具备、缺失、或仅部分对齐的键位
3. 优先补主流程键位：帮助、导航、模式切换、overlay 入口、消息区交互
4. 统一 help 文案、状态栏提示、实际绑定三者一致性
5. 补充快捷键回归测试或最小交互 smoke case

### 6. Speculation / pipelined suggestions 接入

1. 审计现有 `SpeculationState` schema 与 query runtime 接口
2. 明确 Python 侧 speculation 的最小可用接入点
3. 在 suggestion engine / prompt UI 中接入 speculation 状态展示
4. 定义 speculation 接受、取消、失效时的 UI 行为
5. 补充对应测试，避免与现有 suggestion 流冲突

## 运行时深度

### 7. MCP 真实连接补全

1. 核对当前已接通的 SSE / WebSocket IDE transport 路径
2. 梳理 SDK transport 缺失点与外部 `sdk_message_handler` 依赖边界
3. 完成 SDK transport 接入或明确降级路径
4. 验证 claudeai-proxy / SDK / IDE transport 三条链路行为一致性
5. 补充 MCP 真实连接回归测试

### 8. Hook 深度补全

1. 审计当前 `async: True` hook 实现与返回语义
2. 设计 `asyncRewake` 的 Python 对齐方案
3. 实现唤醒链路、状态传播与错误处理
4. 补充 hook 异步行为测试

## 测试与可靠性

### 9. TUI 自动化测试

1. 建立 pytest + textual 测试基础设施
2. 为 PromptInput / PromptFooter / REPLScreen 增加核心交互测试
3. 覆盖 suggestion 导航、overlay 打开关闭、状态栏更新、焦点恢复
4. 补充窄屏/矮屏布局测试

### 10. CLI + TUI 集成测试

1. 设计 `--tui` 启动到 prompt 提交的最小集成用例
2. 覆盖流式响应写入主消息区
3. 覆盖 overlay 交互与返回主 REPL
4. 覆盖异常路径、取消路径与关闭流程

---

## 风险注意事项

1. **TUI 不要再走两套壳层**：现有 `PyClawApp` + `REPLScreen` 架构已收敛，继续在其内迭代
2. **Textual 不等于 Ink/React**：TS 的 hook/context 模式不能直接翻译，要按 Textual 的 widget/message/reactive 模型重新建模
3. **Python 测试注意编码**：Windows 下 pytest 可能遇到 GBK 解码问题，输出捕获时注意
4. **Shell completion Windows 降级**：Windows 下 `get_shell_type()` 返回 `UNKNOWN`，`get_shell_completions()` 静默返回空列表——预期行为
