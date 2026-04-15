# messages

## 模块职责

`messages/` 模块是 py-claw 运行时的消息处理引擎，负责消息创建、规范化、合并、过滤和 SDK 转换。相当于 TypeScript 参考树中的 `ClaudeCode-main/src/utils/messages.ts`。

## 子模块导航

- `types.py` — 核心消息类型定义（UserMessage、AssistantMessage、SystemMessage 等）
- `constants.py` — 消息常量（拒绝/取消消息、合成消息标记）
- `factories.py` — 消息工厂函数（创建各类消息）
- `utils.py` — 工具函数（文本提取、UUID 生成、XML 标签处理）
- `normalization.py` — 消息规范化函数（多通路规范化管道）
- `mappers.py` — SDK 消息格式转换（内部格式 ↔ SDK 格式）

## 关键功能

### 消息类型
- `UserMessage` — 用户消息
- `AssistantMessage` — 助手消息
- `SystemMessage` — 系统消息（支持多种子类型）
- `ProgressMessage` — 进度消息（流式工具更新）
- `AttachmentMessage` — 附件消息
- `HookResultMessage` — Hook 结果消息
- `ToolUseSummaryMessage` — 工具使用摘要
- `TombstoneMessage` — 墓碑消息（已删除内容）

### 核心规范化 (`normalize_messages_for_api`)
多通路规范化管道：
1. 过滤虚拟消息
2. 合并连续的用户消息
3. 规范化工具输入
4. 过滤孤立 thinking 消息
5. 从最后助手消息过滤尾部 thinking
6. 过滤纯空白助手消息
7. 确保助手消息内容非空

### SDK 转换 (`mappers.py`)
- `to_internal_messages()` — SDK 消息 → 内部格式
- `to_sdk_messages()` — 内部格式 → SDK 消息
- `normalize_assistant_message_for_sdk()` — SDK 消费用的助手消息规范化

## 变更记录

- 2026-04-13：创建 messages 模块，实现 L1 功能（消息工具）
