# Claude in Chrome

Use when the user wants to set up, configure, or troubleshoot the Claude in Chrome browser extension.

## What This Skill Does

1. **Detect Chrome extension installation** - Check if the Claude Chrome extension is installed
2. **Configure browser integration** - Set up MCP server for Chrome communication
3. **Troubleshoot connection issues** - Diagnose and fix common Chrome extension problems
4. **Manage permissions** - Configure Claude's access within Chrome

## Prerequisites

- Chrome, Brave, Arc, Edge, Chromium, Vivaldi, or Opera browser
- Claude Code desktop application
- Chrome extension installed from claude.ai/chrome

## Setup Steps

### 1. Install the Chrome Extension

Visit [claude.ai/chrome](https://claude.ai/chrome) to install the extension.

### 2. Enable Claude in Chrome

Run `/chrome` command in Claude Code to enable the integration.

### 3. Configure Browser Detection

The extension supports multiple Chromium-based browsers:
- Chrome (default)
- Brave
- Arc
- Edge
- Chromium
- Vivaldi
- Opera

## Common Issues

### Extension Not Detected

If the extension is not detected:
1. Check that the extension is installed and enabled
2. Reload the browser tab
3. Restart Claude Code

### Connection Problems

For connection issues:
1. Ensure both Claude Code and Chrome are running
2. Check that native messaging is enabled in Chrome
3. Try reconnecting via the extension popup

### Permissions

The extension requires permission to:
- Read page content (for context)
- Send messages to Claude Code
- Access clipboard (for sharing)

## Browser Detection

Claude Code automatically detects available browsers in this order:
1. Chrome (most tested)
2. Brave
3. Arc (macOS only)
4. Edge
5. Chromium
6. Vivaldi
7. Opera

## Platform Support

| Feature | macOS | Linux | Windows | WSL |
|---------|-------|-------|---------|-----|
| Chrome | Yes | Yes | Yes | Yes |
| Brave | Yes | Yes | Yes | No |
| Arc | Yes | No | Yes | No |
| Edge | Yes | Yes | Yes | No |
| Chromium | Yes | Yes | Yes | Yes |
| Vivaldi | Yes | Yes | Yes | No |
| Opera | Yes | Yes | Yes | No |

## Technical Details

### Native Messaging

Claude in Chrome uses native messaging to communicate:
- macOS: `~/Library/Application Support/Claude/claude_in_chrome_mac`
- Linux: `~/.config/Claude/claude_in_chrome_linux`
- Windows: `%APPDATA%/Claude/claude_in_chrome_windows.exe`

### MCP Server Configuration

The extension registers an MCP server named `claude-in-chrome` that provides:
- Page context retrieval
- Content summarization
- Tab management
