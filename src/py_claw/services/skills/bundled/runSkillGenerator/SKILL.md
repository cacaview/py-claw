# Skill Generator

Help users create new custom skills by interviewing them about their workflow and generating a complete SKILL.md file.

## Purpose

Convert a repeatable workflow or process into a reusable skill that can be invoked with `/skill-name`. The generator interviews the user to capture all necessary details.

## When to Use

Use when:
- User wants to create a custom skill
- A repeatable process should be automated as a skill
- User says "create a skill", "make this a skill", or "automate this workflow"
- User has a workflow they run repeatedly

## How It Works

### Step 1: Discover the Workflow

Ask the user to describe:
1. What the skill should do (name and purpose)
2. When it should be used (trigger scenarios)
3. What steps it performs
4. What tools it needs
5. Any inputs or parameters

### Step 2: Design the Skill

Based on the workflow description:
1. Choose an appropriate skill name
2. Write a clear description and "when to use" section
3. Define the workflow steps
4. Identify required tools
5. Specify any parameters

### Step 3: Generate the SKILL.md

Create a complete SKILL.md file with:

```markdown
# Skill Name

Brief description of what this skill does.

## Purpose

When to use this skill.

## How to Use

Step-by-step instructions.

## Parameters

Any inputs this skill accepts.

## Notes

Important considerations or limitations.
```

### Step 4: Save and Register

Save the SKILL.md to the appropriate skills directory:
- User skills: `~/.claude/skills/`
- Project skills: `.claude/skills/`

## Interview Questions

Use AskUserQuestion to gather:

1. **Name**: "What should we call this skill?" (or infer from workflow)
2. **Trigger**: "When should someone use this skill? What would prompt them to invoke it?"
3. **Steps**: "What are the exact steps this skill performs?"
4. **Tools**: "What tools does this skill need access to? (Read, Edit, Bash, Agent, etc.)"
5. **Parameters**: "Does this skill need any inputs from the user?"
6. **Examples**: "Can you give an example of how this skill would be used?"

## Skill Template Structure

```markdown
# {Skill Name}

{One-paragraph description of the skill's purpose.}

## When to Use

{When the user should invoke this skill. Be specific about scenarios.}

## How to Use

{Detailed steps the skill follows. Numbered or bulleted.}

## Parameters

{Any arguments or inputs the skill accepts.}

## Examples

```
/skillname
/skillname arg1
```

## Notes

{Any caveats, limitations, or important considerations.}
```

## Tips for Good Skills

1. **Clear purpose**: One skill, one job
2. **Specific triggers**: When should this be used vs. other skills?
3. **Actionable steps**: Clear numbered steps
4. **Right tools**: Only request tools actually needed
5. **Realistic scope**: Don't try to do too much in one skill

## Output

The skill generator will:
1. Interview the user to understand the workflow
2. Create a complete SKILL.md file
3. Save it to the skills directory
4. Confirm the skill is ready to use

## Notes

- The skillify skill performs a similar function but focuses on converting existing session processes
- This generator is for creating skills from scratch based on user description
- Skills are saved as Markdown files in `.claude/skills/` directories
