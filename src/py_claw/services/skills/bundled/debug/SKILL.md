# Debug Skill

Debug your current Claude Code session by reading the session debug log.

## What This Skill Does

1. **Read the debug log** - Located at `~/.claude/debug/<session-id>.txt`
2. **Analyze for errors/warnings** - Look for [ERROR], [WARN], and notable issues
3. **Provide diagnostics** - Explain what problems were found
4. **Suggest fixes** - Recommend concrete next steps

## Debug Log Location

The debug log is typically at: `~/.claude/debug/<session-id>.txt`

## How Debug Logging Works

- Debug logging captures all events in a session
- Logs grow unbounded in long sessions
- Only the last ~20 lines are shown by default to avoid memory issues
- For full log analysis, use grep for [ERROR] and [WARN] patterns

## Common Issues to Look For

### Errors (must be fixed)
- Permission denied errors
- Tool execution failures
- Network/API errors
- MCP server connection issues

### Warnings (may cause problems)
- Missing dependencies
- Slow operations
- Deprecated API usage
- Configuration issues

## Investigation Steps

1. **Read the last 20 lines** of the debug log
2. **Grep for [ERROR]** across the full file
3. **Grep for [WARN]** across the full file
4. **Check stack traces** if present
5. **Identify failure patterns**

## Settings Locations

For reference, settings are stored in:
- User: `~/.claude/settings.json`
- Project: `.claude/settings.json`
- Local: `.claude/settings.local.json`

## Output Format

When you find issues, present them clearly:
- What happened (error/warning type)
- Where it occurred (file, line if available)
- Why it matters (impact on functionality)
- How to fix (concrete next steps)

## Example

```
Debug Session Report
==================

Found 2 issues:

1. [ERROR] Permission denied: Write tool blocked
   File: ~/.claude/settings.json
   Impact: Cannot write to project files
   Fix: Add "Write" to permissions.allow array

2. [WARN] Slow operation detected
   Operation: git status
   Duration: 5.2s
   Impact: Session may feel sluggish
   Fix: Consider using --fast flag
```

## Tips

- Enable debug logging with `claude --debug` to capture startup events
- For repeated issues, restart with fresh session to isolate
- Check settings files for configuration problems
- Review recent changes to settings or environment
