# Keybindings Skill

Create or modify `~/.claude/keybindings.json` to customize keyboard shortcuts.

## CRITICAL: Read Before Write

**Always read `~/.claude/keybindings.json` first** (it may not exist yet). Merge changes with existing bindings — never replace the entire file.

- Use **Edit** tool for modifications to existing files
- Use **Write** tool only if the file does not exist yet

## File Format

```json
{
  "$schema": "https://www.schemastore.org/claude-code-keybindings.json",
  "$docs": "https://code.claude.com/docs/en/keybindings",
  "bindings": [
    {
      "context": "Chat",
      "bindings": {
        "ctrl+e": "chat:externalEditor"
      }
    }
  ]
}
```

Always include the `$schema` and `$docs` fields.

## Keystroke Syntax

**Modifiers** (combine with `+`):
- `ctrl` (alias: `control`)
- `alt` (aliases: `opt`, `option`) — note: `alt` and `meta` are identical in terminals
- `shift`
- `meta` (aliases: `cmd`, `command`)

**Special keys**: `escape`/`esc`, `enter`/`return`, `tab`, `space`, `backspace`, `delete`, `up`, `down`, `left`, `right`

**Chords**: Space-separated keystrokes, e.g. `ctrl+k ctrl+s` (1-second timeout between keystrokes)

**Examples**: `ctrl+shift+p`, `alt+enter`, `ctrl+k ctrl+n`

## Unbinding Default Shortcuts

Set a key to `null` to remove its default binding:

```json
{
  "context": "Chat",
  "bindings": {
    "ctrl+s": null
  }
}
```

## How User Bindings Interact with Defaults

- User bindings are **additive** — they are appended after the default bindings
- To **move** a binding to a different key: unbind the old key (`null`) AND add the new binding
- A context only needs to appear in the user's file if they want to change something in that context

## Common Patterns

### Rebind a key
To change the external editor shortcut from `ctrl+g` to `ctrl+e`:
```json
{
  "context": "Chat",
  "bindings": {
    "ctrl+g": null,
    "ctrl+e": "chat:externalEditor"
  }
}
```

### Add a chord binding
```json
{
  "context": "Global",
  "bindings": {
    "ctrl+k ctrl+t": "app:toggleTodos"
  }
}
```

## Behavioral Rules

1. Only include contexts the user wants to change (minimal overrides)
2. Validate that actions and contexts are from the known lists below
3. Warn the user proactively if they choose a key that conflicts with reserved shortcuts or common tools like tmux (`ctrl+b`) and screen (`ctrl+a`)
4. When adding a new binding for an existing action, the new binding is additive (existing default still works unless explicitly unbound)
5. To fully replace a default binding, unbind the old key AND add the new one

## Validation with /doctor

The `/doctor` command includes a "Keybinding Configuration Issues" section that validates `~/.claude/keybindings.json`.

### Common Issues and Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `keybindings.json must have a "bindings" array` | Missing wrapper object | Wrap bindings in `{ "bindings": [...] }` |
| `"bindings" must be an array` | `bindings` is not an array | Set `"bindings"` to an array: `[{ context: ..., bindings: ... }]` |
| `Unknown context "X"` | Typo or invalid context name | Use exact context names from the Available Contexts table |
| `Duplicate key "X" in Y bindings` | Same key defined twice in one context | Remove the duplicate; JSON uses only the last value |
| `"X" may not work: ...` | Key conflicts with terminal/OS reserved shortcut | Choose a different key (see Reserved Shortcuts section) |
| `Could not parse keystroke "X"` | Invalid key syntax | Check syntax: use `+` between modifiers, valid key names |
| `Invalid action for "X"` | Action value is not a string or null | Actions must be strings like `"app:help"` or `null` to unbind |

### Example /doctor Output

```
Keybinding Configuration Issues
Location: ~/.claude/keybindings.json
  └ [Error] Unknown context "chat"
    → Valid contexts: Global, Chat, Autocomplete, ...
  └ [Warning] "ctrl+c" may not work: Terminal interrupt (SIGINT)
```

**Errors** prevent bindings from working and must be fixed. **Warnings** indicate potential conflicts but the binding may still work.

## Available Contexts

| Context | Description |
|---------|-------------|
| `Global` | Active everywhere, regardless of focus |
| `Chat` | When the chat input is focused |
| `Autocomplete` | When autocomplete menu is visible |
| `Confirmation` | When a confirmation/permission dialog is shown |
| `Help` | When the help overlay is open |
| `Transcript` | When viewing the transcript |
| `HistorySearch` | When searching command history (ctrl+r) |
| `Task` | When a task/agent is running in the foreground |
| `ThemePicker` | When the theme picker is open |
| `Settings` | When the settings menu is open |
| `Tabs` | When tab navigation is active |
| `Attachments` | When navigating image attachments in a select dialog |
| `Footer` | When footer indicators are focused |
| `MessageSelector` | When the message selector (rewind) is open |
| `DiffDialog` | When the diff dialog is open |
| `ModelPicker` | When the model picker is open |
| `Select` | When a select/list component is focused |
| `Plugin` | When the plugin dialog is open |

## Available Actions

### Global Context Actions
- `app:interrupt` — Interrupt current operation
- `app:exit` — Exit Claude Code
- `app:toggleTodos` — Toggle todo list
- `app:toggleTranscript` — Toggle transcript view
- `app:toggleBrief` — Toggle brief mode
- `app:toggleTeammatePreview` — Toggle teammate preview
- `app:toggleTerminal` — Toggle terminal panel
- `app:redraw` — Redraw screen
- `app:globalSearch` — Global search
- `app:quickOpen` — Quick open

### History Actions
- `history:search` — Search history
- `history:previous` — Previous history item
- `history:next` — Next history item

### Chat Actions
- `chat:cancel` — Cancel current input
- `chat:killAgents` — Kill running agents
- `chat:cycleMode` — Cycle through modes
- `chat:modelPicker` — Open model picker
- `chat:fastMode` — Toggle fast mode
- `chat:thinkingToggle` — Toggle thinking display
- `chat:submit` — Submit message
- `chat:newline` — Insert newline
- `chat:undo` — Undo
- `chat:externalEditor` — Open external editor
- `chat:stash` — Stash message
- `chat:imagePaste` — Paste image
- `chat:messageActions` — Message actions menu

### Autocomplete Actions
- `autocomplete:accept` — Accept suggestion
- `autocomplete:dismiss` — Dismiss suggestions
- `autocomplete:previous` — Previous suggestion
- `autocomplete:next` — Next suggestion

### Confirmation Actions
- `confirm:yes` — Confirm yes
- `confirm:no` — Confirm no
- `confirm:previous` — Previous option
- `confirm:next` — Next option
- `confirm:nextField` — Next field
- `confirm:previousField` — Previous field
- `confirm:cycleMode` — Cycle mode
- `confirm:toggle` — Toggle
- `confirm:toggleExplanation` — Toggle explanation

### Tabs Actions
- `tabs:next` — Next tab
- `tabs:previous` — Previous tab

### Transcript Actions
- `transcript:toggleShowAll` — Toggle show all
- `transcript:exit` — Exit transcript

### History Search Actions
- `historySearch:next` — Next result
- `historySearch:accept` — Accept result
- `historySearch:cancel` — Cancel search
- `historySearch:execute` — Execute command

### Task Actions
- `task:background` — Send task to background

### Theme Actions
- `theme:toggleSyntaxHighlighting` — Toggle syntax highlighting

### Help Actions
- `help:dismiss` — Dismiss help

### Attachment Actions
- `attachments:next` — Next attachment
- `attachments:previous` — Previous attachment
- `attachments:remove` — Remove attachment
- `attachments:exit` — Exit attachments

### Footer Actions
- `footer:up` — Move up
- `footer:down` — Move down
- `footer:next` — Next item
- `footer:previous` — Previous item
- `footer:openSelected` — Open selected
- `footer:clearSelection` — Clear selection
- `footer:close` — Close footer

### Message Selector Actions
- `messageSelector:up` — Move up
- `messageSelector:down` — Move down
- `messageSelector:top` — Go to top
- `messageSelector:bottom` — Go to bottom
- `messageSelector:select` — Select message

### Diff Dialog Actions
- `diff:dismiss` — Dismiss dialog
- `diff:previousSource` — Previous source
- `diff:nextSource` — Next source
- `diff:back` — Go back
- `diff:viewDetails` — View details
- `diff:previousFile` — Previous file
- `diff:nextFile` — Next file

### Model Picker Actions
- `modelPicker:decreaseEffort` — Decrease effort
- `modelPicker:increaseEffort` — Increase effort

### Select Actions
- `select:next` — Next item
- `select:previous` — Previous item
- `select:accept` — Accept selection
- `select:cancel` — Cancel selection

### Plugin Actions
- `plugin:toggle` — Toggle plugin dialog
- `plugin:install` — Install plugin

### Permission Actions
- `permission:toggleDebug` — Toggle debug

### Settings Actions
- `settings:search` — Search settings
- `settings:retry` — Retry
- `settings:close` — Close settings

### Voice Actions
- `voice:pushToTalk` — Push to talk

## Reserved Shortcuts

### Non-rebindable (will cause errors)
- `ctrl+c` — Terminal interrupt (SIGINT)
- `ctrl+d` — Exit (EOF)
- `ctrl+z` — Suspend process (SIGTSTP)

### Terminal reserved (may conflict)
- `ctrl+b` — tmux default prefix
- `ctrl+a` — screen default prefix
- `ctrl+q` — XON (flow control)
- `ctrl+s` — XOFF (flow control)
- `ctrl+v` — Terminal literal prefix
- `ctrl+\`` — Quit (SIGQUIT)

### macOS reserved (will cause errors)
- `cmd+tab` — Application switcher
- `cmd+` — Various system shortcuts
