# Schedule Remote Agents

Create, update, list, or run scheduled remote Claude Code agents that execute on a cron schedule in Anthropic's cloud infrastructure.

## Purpose

Schedule recurring tasks that run as fully isolated remote sessions (CCR - Claude Code Remote). Each trigger spawns an agent in a sandboxed environment with its own git checkout, tools, and optional MCP connections.

## When to Use

Use when the user wants to:
- Schedule a recurring remote agent (e.g., "every weekday at 9am")
- Set up automated tasks that run on a cron schedule
- Create a cron job for Claude Code
- Manage their scheduled agents/triggers

## Tools Available

Use the following tools to manage triggers:
- `RemoteTrigger` with `action: "list"` — list all triggers
- `RemoteTrigger` with `action: "get", trigger_id: "..."` — fetch one trigger
- `RemoteTrigger` with `action: "create", body: {...}` — create a trigger
- `RemoteTrigger` with `action: "update", trigger_id: "...", body: {...}` — partial update
- `RemoteTrigger` with `action: "run", trigger_id: "..."` — run a trigger now

## Workflows

### CREATE a new trigger

1. **Understand the goal** — Ask what they want the remote agent to do. What repo(s)? What task?
2. **Craft the prompt** — Help them write an effective agent prompt. Good prompts are:
   - Specific about what to do and what success looks like
   - Clear about which files/areas to focus on
   - Explicit about what actions to take (open PRs, commit, just analyze, etc.)
3. **Set the schedule** — Ask when and how often. Cron expressions are in UTC. Minimum interval is 1 hour.
4. **Choose the model** — Default to `claude-sonnet-4-6`.
5. **Validate connections** — Check if MCP connectors are needed (e.g., Datadog, Slack).
6. **Review and confirm** — Show the full configuration before creating.
7. **Create it** — Call `RemoteTrigger` with `action: "create"` and show the result.

### UPDATE a trigger

1. List triggers first so they can pick one
2. Ask what they want to change
3. Show current vs proposed value
4. Confirm and update

### LIST triggers

1. Call `RemoteTrigger` with `action: "list"`
2. Display in readable format: name, schedule, enabled/disabled, next run, repo(s)

### RUN NOW

1. List triggers if they haven't specified which one
2. Confirm which trigger
3. Execute and confirm

## Trigger Configuration

### Create body shape

```json
{
  "name": "AGENT_NAME",
  "cron_expression": "CRON_EXPR",
  "enabled": true,
  "job_config": {
    "ccr": {
      "environment_id": "ENVIRONMENT_ID",
      "session_context": {
        "model": "claude-sonnet-4-6",
        "sources": [
          {"git_repository": {"url": "https://github.com/ORG/REPO"}}
        ],
        "allowed_tools": ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
      },
      "events": [
        {"data": {
          "uuid": "<lowercase v4 uuid>",
          "session_id": "",
          "type": "user",
          "parent_tool_use_id": null,
          "message": {"content": "PROMPT_HERE", "role": "user"}
        }}
      ]
    }
  }
}
```

Generate a fresh lowercase UUID for `events[].data.uuid` yourself.

### Required Fields

- `name` (string) — A descriptive name
- `cron_expression` (string) — 5-field cron. **Minimum interval is 1 hour.**
- `job_config` (object) — Session configuration

### Optional Fields

- `enabled` (boolean, default: true)
- `mcp_connections` (array) — MCP servers to attach:
  ```json
  [{"connector_uuid": "uuid", "name": "server-name", "url": "https://..."}]
  ```

### Cron Expression Examples

- `0 9 * * 1-5` — Every weekday at 9am UTC
- `0 */2 * * *` — Every 2 hours
- `0 0 * * *` — Daily at midnight UTC
- `30 14 * * 1` — Every Monday at 2:30pm UTC
- `0 8 1 * *` — First of every month at 8am UTC

Minimum interval is 1 hour. `*/30 * * * *` will be rejected.

## Important Notes

- These are **REMOTE agents** — they run in Anthropic's cloud, not on the user's machine
- They cannot access local files, local services, or local environment variables
- The prompt is the most important part — spend time getting it right
- To delete a trigger, direct users to https://claude.ai/code/scheduled
- Generate fresh UUIDs for trigger events

## Prerequisites

1. User must be authenticated with a claude.ai account (run `/login` first)
2. Remote sessions must be allowed by organization policy
3. For GitHub access, the Claude GitHub App must be installed on the repo

## Error Handling

- **Not authenticated**: "Run /login, then try /schedule again"
- **Policy denied**: "Remote sessions are not allowed by your organization policy"
- **No environments**: Create a default environment or direct to https://claude.ai/code
