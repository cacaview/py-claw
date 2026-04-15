# Memory Review

Review the user's memory landscape and produce a clear report of proposed changes.

## Goal

Review auto-memory entries and propose promotions to CLAUDE.md, CLAUDE.local.md, or shared memory. Also detects outdated, conflicting, and duplicate entries across memory layers.

## Memory Layers

| Layer | Location | Purpose |
|-------|----------|---------|
| **CLAUDE.md** | Project root | Project conventions for all contributors |
| **CLAUDE.local.md** | Project root | Personal instructions for this user only |
| **Auto-memory** | System prompt | Session-specific working notes |
| **Team memory** | Configured path | Org-wide knowledge across repos |

## Memory Layer Purposes

### CLAUDE.md
Project conventions and instructions for Claude that **all contributors** should follow:
- "use bun not npm"
- "API routes use kebab-case"
- "test command is bun test"
- "prefer functional style"

### CLAUDE.local.md
Personal instructions for Claude **specific to this user**:
- "I prefer concise responses"
- "always explain trade-offs"
- "don't auto-commit"
- "run tests before committing"

### Team Memory
Org-wide knowledge that **applies across repositories**:
- "deploy PRs go through #deploy-queue"
- "staging is at staging.internal"
- "platform team owns infra"

### Auto-memory
Working notes, temporary context, or entries that **don't clearly fit elsewhere**:
- Session-specific observations
- Uncertain patterns
- Temporary reminders

## What NOT to Include

- Editor theme preferences (not Claude instructions)
- IDE keybindings (not Claude instructions)
- External tool preferences

## Classification Rules

For each auto-memory entry, determine the best destination:

| If entry is... | Then... |
|-----------------|---------|
| Project convention | → CLAUDE.md |
| Personal preference for Claude | → CLAUDE.local.md |
| Org-wide knowledge | → Team memory (if configured) |
| Working notes/temporary | → Stay in auto-memory |
| Uncertain | → Ask user |

## Cleanup Opportunities

### Duplicates
Auto-memory entries already captured in CLAUDE.md or CLAUDE.local.md → propose removing from auto-memory

### Outdated
CLAUDE.md or CLAUDE.local.md entries contradicted by newer auto-memory → propose updating

### Conflicts
Contradictions between layers → propose resolution noting which is more recent

## Report Format

Present findings grouped by action type:

1. **Promotions** — entries to move, with destination and rationale
2. **Cleanup** — duplicates, outdated entries, conflicts
3. **Ambiguous** — entries needing user input
4. **No action needed** — entries that should stay put

## Rules

- Present ALL proposals before making changes
- Do NOT modify files without explicit user approval
- Do NOT create new files unless target doesn't exist
- Ask about ambiguous entries — don't guess
