# Stuck Skill

Diagnose frozen, stuck, or very slow Claude Code sessions.

## Overview

When the user thinks another Claude Code session is frozen or stuck, investigate and report the findings.

## Signs of a Stuck Session

- **High CPU (≥90%) sustained** — likely an infinite loop
- **Process state `D`** (uninterruptible sleep) — often an I/O hang
- **Process state `T`** (stopped) — user probably hit Ctrl+Z accidentally
- **Process state `Z`** (zombie) — parent isn't reaping
- **Very high RSS (≥4GB)** — possible memory leak
- **Stuck child process** — hung git, node, or shell subprocess

## Investigation Steps

### 1. List all Claude Code processes

**Linux/macOS:**
```bash
ps -axo pid=,pcpu=,rss=,etime=,state=,comm=,command= | grep -E '(claude|cli)' | grep -v grep
```

Filter to rows where `comm` is `claude` or (`cli` AND command path contains "claude").

### 2. For suspicious processes

- Child processes: `pgrep -lP <pid>`
- If high CPU: sample again after 1-2s to confirm
- Full command line: `ps -p <child_pid> -o command=`
- Debug log tail: `~/.claude/debug/<session-id>.txt`

### 3. Stack dump (advanced, optional)

**macOS:**
```bash
sample <pid> 3
```

This is large — only if the process is clearly hung.

## Report Structure

### If healthy
Tell the user directly — do NOT post to Slack.

### If found issues

Post to **#claude-code-feedback** (channel ID: C07VBSHV7EV) using the Slack MCP tool.

**Two-message structure:**

1. **Top-level message** — one short line:
   - hostname, Claude Code version, terse symptom
   - e.g., "session PID 12345 pegged at 100% CPU for 10min"

2. **Thread reply** — full diagnostic dump with:
   - PID, CPU%, RSS, state, uptime, command line
   - Diagnosis of what's likely wrong
   - Debug log tail or sample output if captured

## Rules

- **Do NOT kill or signal processes** — this is diagnostic only
- If user provided an argument (e.g., specific PID), focus there
- Only post to Slack if you found something — healthy sessions get direct response

## Notes

- Exclude the current process from analysis
- Process names: `claude` (installed) or `cli` (native dev build)
- The `state` column first character indicates status (ignore modifiers like `+`, `s`, `<`)
