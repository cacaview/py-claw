# Batch: Parallel Work Orchestration

Orchestrate a large, parallelizable change across this codebase using isolated worktree agents.

## Overview

This skill helps you break down large-scale changes (migrations, refactors, bulk renames) into independent units that can be executed in parallel by multiple agents, each creating their own PR.

## When to Use

Use when:
- Making sweeping mechanical changes across many files
- Performing migrations (e.g., React to Vue, lodash to native)
- Adding type annotations across a codebase
- Any change that can be decomposed into independent parallel units

## Prerequisites

- Must be run in a **git repository** (uses isolated git worktrees)
- Each unit must be **independently mergeable** without depending on another unit's PR

## Phase 1: Research and Plan

1. **Understand the scope** - Research what files, patterns, and call sites need to change
2. **Decompose into units** - Break work into 5-30 self-contained units:
   - Each unit must be independently implementable in an isolated git worktree
   - Each unit must be mergeable on its own
   - Prefer per-directory or per-module slicing
3. **Determine verification** - Figure out how workers can verify their change works:
   - UI changes: browser automation or screenshot
   - CLI changes: launch app interactively
   - API changes: start server and test endpoints
   - Unit tests: run test suite
4. **Write the plan** - Document:
   - Summary of scope
   - Numbered list of work units with files/directories
   - Verification recipe
   - Worker instructions template

## Phase 2: Execute in Parallel

Spawn one background agent per work unit using the **Agent** tool with `isolation: "worktree"`.

For each agent, provide:
- Overall goal and instruction
- Specific task (title, file list, change description)
- Codebase conventions to follow
- Verification recipe
- Worker instructions

## Worker Instructions Template

Each worker should:
1. **Simplify** - Review changes with the `simplify` skill
2. **Run tests** - Run project's test suite (npm test, pytest, go test, etc.)
3. **Test end-to-end** - Follow the verification recipe
4. **Commit and push** - Create a descriptive commit, push branch, create PR
5. **Report** - End with `PR: <url>` so coordinator can track

## Phase 3: Track Progress

Render a status table as agents complete:

| # | Unit | Status | PR |
|---|------|--------|----|
| 1 | change-a | done | https://... |
| 2 | change-b | running | — |
| 3 | change-c | failed | — |

Update as completion notifications arrive. Final summary: "22/24 units landed as PRs".

## Example

```
/batch migrate from react to vue
/batch replace all uses of lodash with native equivalents
/batch add type annotations to all untyped function parameters
```

## Requirements

- Git repository (for worktree isolation)
- Multiple files/modules to change (not suitable for tiny changes)
- Each unit must be independently valid

## Notes

- Units should be roughly uniform in size
- Large files → fewer units; many small files → more units
- If not a git repo, this skill cannot run
