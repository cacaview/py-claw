# cron/

## 模块职责

`src/py_claw/services/cron/` 提供 cron 表达式解析和下次执行时间计算，基于 `ClaudeCode-main/src/utils/cron.ts` 实现。

## 入口

- `__init__.py` - 公开 API 导出
- `cron.py` - 主要实现

## 核心功能

### Cron 解析

- `parse_cron_expression()` - 解析 5 字段 cron 表达式为 CronFields
- 支持语法：通配符、N、step (*/N)、range (N-M)、列表 (N,M,...)

### 下次执行计算

- `compute_next_cron_run()` - 计算给定时间之后下一次匹配的时间
- 使用本地时区，逐分钟向前遍历，最多 366 天
- 标准 cron 语义：dayOfMonth 和 dayOfWeek 都约束时，任意一个匹配即可

### 人类可读格式

- `cron_to_human()` - 将 cron 表达式转换为人类可读字符串
- 支持常见模式：每 N 分钟、每小时、每天、每周几、工作日
- `utc` 选项用于 CCR 远程触发器

## 类型

- `CronFields` - 解析后的 cron 字段（immutable dataclass）

## 字段范围

| 字段 | 范围 |
|------|------|
| minute | 0-59 |
| hour | 0-23 |
| dayOfMonth | 1-31 |
| month | 1-12 |
| dayOfWeek | 0-6（0=周日，7 也接受为周日别名）|
