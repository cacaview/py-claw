# Hunter Skill

Track down and analyze artifacts, issues, and code quality problems across the codebase. Use systematic investigation to find bugs, code smells, and improvement opportunities.

## Purpose

Systematically hunt for:
- Bugs and defects hiding in code
- Code smells and technical debt
- Security vulnerabilities
- Performance issues
- Missing tests or documentation

## When to Use

Use when:
- The user wants to "hunt" for bugs or issues
- Performing code review and quality analysis
- Tracking down a persistent problem
- Looking for improvement opportunities across the codebase

## How It Works

### Investigation Phases

#### 1. Scout the Territory
- Understand the codebase structure
- Identify key areas and their responsibilities
- Map out dependencies and data flows

#### 2. Look for Signs
Common indicators of problems:
- Inconsistent naming conventions
- Deep nesting or complex conditionals
- Magic numbers or hardcoded values
- Missing error handling
- Large functions doing too much
- Duplicated code patterns

#### 3. Track the Trail
Follow connections:
- How does data flow through the system?
- Where are the boundaries between components?
- What assumptions are being made?

#### 4. Capture Findings
Document discoveries:
- Location and nature of each issue
- Severity assessment
- Suggested remediation

## Investigation Techniques

### Pattern Recognition
```
Common bug patterns:
- Null/not defined checks missing
- Off-by-one errors
- Race conditions
- Resource leaks
- Error swallowing
```

### Code Smell Checklist
```
- Is the code doing too much? (god functions)
- Are names misleading or unclear?
- Is there duplicated logic?
- Are there comments explaining why instead of what?
- Is there dead code?
```

### Security Hunting
```
Look for:
- SQL injection vulnerabilities
- Command injection risks
- Hardcoded credentials
- Improper authentication/authorization
- Missing input validation
```

## Output Format

Present findings in organized categories:

```
# Hunter Report

## Critical Issues (Fix Immediately)
- [file:line] Description of issue

## High Priority (Fix Soon)
- [file:line] Description of issue

## Medium Priority (Plan to Fix)
- [file:line] Description of issue

## Low Priority (Consider Fixing)
- [file:line] Description of issue

## Recommendations
1. Actionable suggestion
2. Actionable suggestion
```

## Rules

- Be thorough but respectful of existing architecture
- Focus on finding issues, not judging developers
- Provide actionable remediation steps
- Consider the context before flagging issues
- Balance bug hunting with feature development needs

## Notes

- Hunter is most effective when you have a specific concern or area to investigate
- For general code review, consider using the `simplify` skill instead
- Always verify findings before reporting as facts
