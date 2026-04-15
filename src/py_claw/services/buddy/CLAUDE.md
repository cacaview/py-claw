[根目录(../../../CLAUDE.md) > [src](../../CLAUDE.md) > [py_claw](../CLAUDE.md) > **services/buddy**

# services/buddy

## 模块职责

`py_claw/services/buddy/` 提供 Companion/Buddy 子系统的完整实现，包括 deterministic roll、ASCII sprite 渲染、notification 触发和 Textual UI 组件。

## 架构概览

```
buddy/
├── types.py          # Companion/Species/Rarity/Eye/Hat 等类型定义
├── companion.py      # Deterministic roll 逻辑 (hash + mulberry32 PRNG)
├── sprites.py        # ASCII sprite 渲染 (每 species 多帧动画)
├── prompt.py         # Prompt 附着 (companion intro attachment)
├── notification.py   # Teaser window 检测 + notification 管理器
├── sprite_widget.py  # Textual UI 组件 (CompanionSpriteWidget/FloatingBubble)
└── service.py        # 服务门面 (companion_reserved_columns 等)
```

## 核心概念

### Deterministic Roll

基于 `hash(userId + SALT)` 的稳定 companion 生成：
- `SALT = "friend-2026-401"` 保证同用户每次获得相同 companion
- `mulberry32()` seeded PRNG 生成确定性的 rarity/species/eye/hat/stats
- 优先级: `oauthAccount.accountUuid > userID > "anon"`

### Teaser Window

April 1-7, 2026 本地时间窗口显示 `/buddy` 彩虹提示：
- `is_buddy_teaser_window()` — 检测是否在 teaser 窗口内
- `is_buddy_live()` — 检测 buddy 功能是否已上线
- `find_buddy_trigger_positions()` — 找到文本中所有 `/buddy` 触发位置

### Notification Manager

`BuddyNotificationManager` 管理所有 buddy 相关通知：
- `add_notification()` — 添加通知，返回 dismiss 函数
- `remove_notification()` — 移除通知
- 自动过期处理

### Textual UI 组件

- `CompanionSpriteWidget` — 主要 companion 显示组件
  - 宽终端: 完整 ASCII sprite + speech bubble
  - 窄终端: 单行 face + quip
  - 500ms tick 驱动动画 (idle/fidget/pet)
  - 自动 dismiss speech bubble (10s)

- `CompanionFloatingBubble` — 全屏浮动气泡
  - 渲染在 bottomFloat 区域
  - 不被 overflow clip

- `companion_reserved_columns()` — 计算 companion 占用的终端列数

## 导出 API

### types (types.py)

| 导出 | 说明 |
|------|------|
| `RARITIES` | rarity 元组 |
| `RARITY_WEIGHTS` | rarity 权重 |
| `RARITY_FLOOR` | rarity 最低属性值 |
| `RARITY_STARS` | rarity 显示星星数 |
| `RARITY_COLORS` | rarity 对应的 Textual 颜色 |
| `SPECIES` | species 元组 |
| `EYES` | eye 字符元组 |
| `HATS` | hat 字符元组 |
| `STAT_NAMES` | 属性名元组 |
| `Companion` | 完整 companion dataclass |
| `CompanionBones` | deterministic bones |
| `CompanionSoul` | model-generated soul |
| `StoredCompanion` | config 存储格式 |
| `Roll` | roll 结果 |

### companion (companion.py)

| 导出 | 说明 |
|------|------|
| `roll()` | 为 user 生成 deterministic roll |
| `roll_with_seed()` | 用显式 seed 生成 roll |
| `companion_user_id()` | 获取 companion user ID |
| `get_companion()` | 从 config 获取完整 companion |
| `clear_roll_cache()` | 清除 roll 缓存 |

### sprites (sprites.py)

| 导出 | 说明 |
|------|------|
| `render_sprite()` | 渲染 sprite 帧 |
| `render_face()` | 渲染单行 face (窄终端用) |
| `sprite_frame_count()` | 获取 species 动画帧数 |

### prompt (prompt.py)

| 导出 | 说明 |
|------|------|
| `companion_intro_text()` | 生成 companion intro 文本 |
| `get_companion_intro_attachment()` | 获取 prompt attachment |

### notification (notification.py)

| 导出 | 说明 |
|------|------|
| `is_buddy_teaser_window()` | 检测 teaser 窗口 |
| `is_buddy_live()` | 检测 buddy 是否上线 |
| `find_buddy_trigger_positions()` | 找到 /buddy 触发位置 |
| `BuddyNotification` | 通知 dataclass |
| `NotificationTrigger` | 触发位置 dataclass |
| `BuddyNotificationManager` | 通知管理器类 |
| `get_notification_manager()` | 获取全局通知管理器 |
| `reset_notification_manager()` | 重置通知管理器 (测试用) |

### sprite_widget (sprite_widget.py)

| 导出 | 说明 |
|------|------|
| `CompanionSpriteWidget` | Textual companion 显示组件 |
| `CompanionFloatingBubble` | 全屏浮动气泡组件 |
| `SpeechBubble` | Speech bubble widget |
| `get_companion_display_width()` | 计算 companion 显示宽度 |

### service (service.py)

| 导出 | 说明 |
|------|------|
| `BuddyConfig` | buddy 配置 dataclass |
| `get_buddy_config()` | 获取全局配置 |
| `set_buddy_config()` | 设置全局配置 |
| `get_companion()` | 获取 companion (service 版本) |
| `render_companion_sprite()` | 渲染 sprite |
| `render_companion_face()` | 渲染 face |
| `get_companion_stats()` | 获取 stats |
| `companion_reserved_columns()` | 计算占用列数 |

## 与 Textual 集成

CompanionSpriteWidget 使用 Textual 的定时器机制:
- 500ms tick 驱动 idle/fidget/pet 动画
- 自动 dismiss bubble (10s)
- 响应式渲染

## 变更记录 (Changelog)

- 2026-04-14：新增 `notification.py` (teaser window + notification manager)、`sprite_widget.py` (Textual UI 组件)、`companion_reserved_columns()` 函数；添加 `RARITY_COLORS` 到 types.py。
