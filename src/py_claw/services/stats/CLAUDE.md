# services/stats

[根文档](../../../../CLAUDE.md) > [py_claw](../../CLAUDE.md) > [services](../CLAUDE.md) > **stats**

# Stats 模块

会话统计聚合工具,来自 `ClaudeCode-main/src/utils/debug.ts`。

## 主要功能

### 统计聚合

- `aggregate_claude_code_stats()` - 聚合所有 Claude Code 会话统计
- `aggregate_claude_code_stats_for_range()` - 按日期范围聚合统计

### 会话开始日期

- `read_session_start_date()` - 快速读取会话文件的开始日期

### Streak 计算

- `calculate_streaks()` - 从日活动数据计算连续天数

### 工具函数

- `to_date_string()` - datetime 转换为 YYYY-MM-DD
- `get_today_date_string()` - 获取今天的日期字符串
- `get_yesterday_date_string()` - 获取昨天的日期字符串
- `is_date_before()` - 比较两个日期
- `get_next_day()` - 获取下一天

### Shot Count 提取 (Ant 专用)

- `extract_shot_count_from_messages()` - 从 gh pr create 调用中提取 shot count

## 关键类型

### DailyActivity

日活动摘要。

```python
@dataclass
class DailyActivity:
    date: str           # YYYY-MM-DD
    message_count: int  # 消息数
    session_count: int  # 会话数
    tool_call_count: int  # 工具调用数
```

### DailyModelTokens

每日每模型 token 使用量。

```python
@dataclass
class DailyModelTokens:
    date: str
    tokens_by_model: dict[str, int]
```

### StreakInfo

连续天数信息。

```python
@dataclass
class StreakInfo:
    current_streak: int
    longest_streak: int
    current_streak_start: str | None
    longest_streak_start: str | None
    longest_streak_end: str | None
```

### SessionStats

单个会话的统计。

```python
@dataclass
class SessionStats:
    session_id: str
    duration: int       # 毫秒
    message_count: int
    timestamp: str       # ISO 时间戳
```

### ModelUsage

模型使用统计。

```python
@dataclass
class ModelUsage:
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    web_search_requests: int
    cost_usd: float
    context_window: int
    max_output_tokens: int
```

### ClaudeCodeStats

完整统计对象。

```python
@dataclass
class ClaudeCodeStats:
    total_sessions: int
    total_messages: int
    total_days: int
    active_days: int
    streaks: StreakInfo
    daily_activity: list[DailyActivity]
    daily_model_tokens: list[DailyModelTokens]
    longest_session: SessionStats | None
    model_usage: dict[str, ModelUsage]
    first_session_date: str | None
    last_session_date: str | None
    peak_activity_day: str | None
    peak_activity_hour: int | None
    total_speculation_time_saved_ms: int
    shot_distribution: dict[int, int] | None
    one_shot_rate: int | None
```

## 日期范围

`StatsDateRange` = `'7d'` | `'30d'` | `'all'`

## 相关文件

- `stats.py` - 统计聚合实现
