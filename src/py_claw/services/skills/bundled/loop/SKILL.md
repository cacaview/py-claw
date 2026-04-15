# Loop Skill

Run a prompt or slash command on a recurring interval.

## Usage

```
/loop [interval] <prompt>
```

**Intervals**: Ns, Nm, Nh, Nd (e.g. 5m, 30m, 2h, 1d). Minimum granularity is 1 minute.
If no interval is specified, defaults to 10m.

**Examples**:
```
/loop 5m /babysit-prs
/loop 30m check the deploy
/loop 1h /standup 1
/loop check the deploy          (defaults to 10m)
/loop check the deploy every 20m
```

## Parsing Rules

1. **Leading token**: if the first whitespace-delimited token matches `^\d+[smhd]$` (e.g. `5m`, `2h`), that's the interval; the rest is the prompt.
2. **Trailing "every" clause**: if the input ends with `every <N><unit>` or `every <N> <unit-word>` (e.g. `every 20m`, `every 5 minutes`), extract that as the interval and strip it from the prompt.
3. **Default**: otherwise, interval is `10m` and the entire input is the prompt.

**Examples**:
- `5m /babysit-prs` → interval `5m`, prompt `/babysit-prs` (rule 1)
- `check the deploy every 20m` → interval `20m`, prompt `check the deploy` (rule 2)
- `check the deploy` → interval `10m`, prompt `check the deploy` (rule 3)
- `check every PR` → interval `10m`, prompt `check every PR` (rule 3 — "every" not followed by time)

## Interval → Cron

Supported suffixes: `s` (seconds), `m` (minutes), `h` (hours), `d` (days).

| Interval pattern | Cron expression | Notes |
|-----------------|----------------|-------|
| `Nm` where N ≤ 59 | `*/N * * * *` | every N minutes |
| `Nm` where N ≥ 60 | `0 */H * * *` | round to hours (H = N/60) |
| `Nh` where N ≤ 23 | `0 */N * * *` | every N hours |
| `Nd` | `0 0 */N * *` | every N days at midnight |
| `Ns` | treat as `ceil(N/60)m` | cron minimum is 1 minute |

**If the interval doesn't cleanly divide** (e.g. `7m` → `*/7 * * * *` gives uneven gaps), pick the nearest clean interval and inform the user.

## Action

1. Call **CronCreate** tool with:
   - `cron`: the cron expression from the table above
   - `prompt`: the parsed prompt verbatim (slash commands passed through unchanged)
   - `recurring`: `true`

2. Confirm: what's scheduled, the cron expression, the cadence, that recurring tasks auto-expire after 7 days, and that they can be cancelled with **CronDelete** (include the job ID).

3. **Then immediately execute the parsed prompt now** — don't wait for the first cron fire. If it's a slash command, invoke it via the Skill tool; otherwise act on it directly.

## Tool Names

- **CronCreate**: Schedule a new recurring task
- **CronDelete**: Cancel a previously scheduled task (provide the job ID)
- **CronList**: List all scheduled cron jobs
