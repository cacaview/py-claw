# Skillify: Session to Skill Converter

Convert a session's repeatable process into a reusable skill.

## Your Task

### Step 1: Analyze the Session

Identify from the conversation:
- What repeatable process was performed
- What the inputs/parameters were
- The distinct steps (in order)
- Success artifacts/criteria for each step
- Where the user corrected or steered you
- What tools and permissions were needed
- What agents were used

### Step 2: Interview the User

Use **AskUserQuestion** for ALL questions. Never ask via plain text.

**Round 1: High level confirmation**
- Suggest a name and description for the skill
- Suggest high-level goal(s) and specific success criteria

**Round 2: More details**
- Present identified steps as a numbered list
- Suggest arguments based on what was observed
- Ask where the skill should be saved:
  - **This repo** (`.claude/skills/<name>/SKILL.md`) — for repo-specific workflows
  - **Personal** (`~/.claude/skills/<name>/SKILL.md`) — for cross-repo workflows

**Round 3: Breaking down each step**
For each major step:
- What does this step produce that later steps need?
- What proves the step succeeded?
- Should the user confirm before proceeding?
- Can any steps run in parallel?
- What tools/execution mode should be used?

**Round 4: Final questions**
- Confirm when this skill should be invoked
- Suggest trigger phrases

### Step 3: Write the SKILL.md

Create the skill at the chosen location:

```markdown
---
name: {{skill-name}}
description: {{one-line description}}
allowed-tools:
  {{list of tool permission patterns}}
when_to_use: {{when to invoke this skill, including trigger phrases}}
argument-hint: "{{hint showing placeholders}}"
arguments:
  {{list of argument names}}
context: {{inline or fork}}
---

# {{Skill Title}}
Description of skill

## Inputs
- `$arg_name`: Description of this input

## Goal
Clearly stated goal for this workflow.

## Steps

### 1. Step Name
What to do in this step.

**Success criteria**: What proves this step is done.
```

**Per-step annotations**:
- **Success criteria**: REQUIRED on every step
- **Execution**: `Direct` (default), `Task agent`, `Teammate`, or `[human]`
- **Artifacts**: Data produced that later steps need
- **Human checkpoint**: When to pause and ask user

### Step 4: Confirm and Save

Before writing, output the complete SKILL.md as a yaml code block for review. Then ask for confirmation.

## Session Context

To get session memory, use `py_claw.services.session_memory` if available.

## Notes

- Use AskUserQuestion for ALL questions
- Don't over-ask for simple processes
- Pay attention to user corrections during the session
- Keep simple skills simple
