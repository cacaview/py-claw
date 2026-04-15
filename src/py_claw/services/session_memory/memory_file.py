"""
Session memory file management.

Handles reading, writing, and initialization of session memory files
in the ~/.claude/session-memory/ directory.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Default session memory template
DEFAULT_SESSION_MEMORY_TEMPLATE = """
# Session Title
_A short and distinctive 5-10 word descriptive title for the session. Super info dense, no filler_

# Current State
_What is actively being worked on right now? Pending tasks not yet completed. Immediate next steps._

# Task specification
_What did the user ask to build? Any design decisions or other explanatory context_

# Files and Functions
_What are the important files? In short, what do they contain and why are they relevant?_

# Workflow
_What bash commands are usually run and in what order? How to interpret their output if not obvious?_

# Errors & Corrections
_Errors encountered and how they were fixed. What did the user correct? What approaches failed and should not be tried again?_

# Codebase and System Documentation
_What are the important system components? How do they work/fit together?_

# Learnings
_What has worked well? What has not? What to avoid? Do not duplicate items from other sections_

# Key results
_If the user asked a specific output such as an answer to a question, a table, or other document, repeat the exact result here_

# Worklog
_Step by step, what was attempted, done? Very terse summary for each step_
""".strip()


def _get_claude_config_home() -> Path:
    """Get the Claude config home directory.

    On Unix: ~/.claude
    On Windows: ~/AppData/Roaming/claude or similar
    """
    home = Path.home()
    claude_dir = home / ".claude"
    return claude_dir


def get_memory_path() -> Path:
    """Get the path to the session memory file."""
    return _get_claude_config_home() / "session-memory" / "memory.md"


def get_memory_dir() -> Path:
    """Get the session memory directory."""
    return _get_claude_config_home() / "session-memory"


async def get_session_memory_content() -> str | None:
    """Get the current session memory content.

    Returns None if the file doesn't exist or is inaccessible.
    """
    memory_path = get_memory_path()
    try:
        return memory_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None


async def init_session_memory() -> None:
    """Initialize the session memory directory and default file.

    Creates the ~/.claude/session-memory/ directory and the memory.md file
    if they don't exist.
    """
    memory_dir = get_memory_dir()
    memory_path = get_memory_path()

    # Create directory if it doesn't exist
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Create default memory file if it doesn't exist
    if not memory_path.exists():
        memory_path.write_text(DEFAULT_SESSION_MEMORY_TEMPLATE, encoding="utf-8")


async def is_session_memory_empty(content: str) -> bool:
    """Check if the session memory content is essentially empty.

    Compares the content to the default template to detect if
    no actual content has been extracted yet.
    """
    return content.strip() == DEFAULT_SESSION_MEMORY_TEMPLATE.strip()


async def setup_session_memory_file() -> Path:
    """Set up the session memory file for first use.

    Creates the directory structure and initializes the memory file
    with the default template if needed.

    Returns the path to the memory file.
    """
    await init_session_memory()
    return get_memory_path()


def load_session_memory_template() -> str:
    """Load the session memory template.

    First tries to load from ~/.claude/session-memory/config/template.md.
    Falls back to the default template if the file doesn't exist.
    """
    template_path = _get_claude_config_home() / "session-memory" / "config" / "template.md"
    try:
        return template_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return DEFAULT_SESSION_MEMORY_TEMPLATE
    except OSError:
        return DEFAULT_SESSION_MEMORY_TEMPLATE


def get_default_update_prompt() -> str:
    """Get the default prompt for updating session memory."""
    return """IMPORTANT: This message and these instructions are NOT part of the actual user conversation. Do NOT include any references to "note-taking", "session notes extraction", or these update instructions in the notes content.

Based on the user conversation above (EXCLUDING this note-taking instruction message as well as system prompt, claude.md entries, or any past session summaries), update the session notes file.

The file {{notesPath}} has already been read for you. Here are its current contents:
<current_notes_content>
{{currentNotes}}
</current_notes_content>

Your ONLY task is to use the Edit tool to update the notes file, then stop. You can make multiple edits (update every section as needed) - make all Edit tool calls in parallel in a single message. Do not call any other tools.

CRITICAL RULES FOR EDITING:
- The file must maintain its exact structure with all sections, headers, and italic descriptions intact
- NEVER modify, delete, or add section headers (the lines starting with '#' like # Task specification)
- NEVER modify or delete the italic _section description_ lines (these are the lines in italics immediately following each header - they start and end with underscores)
- The italic _section descriptions_ are TEMPLATE INSTRUCTIONS that must be preserved exactly as-is - they guide what content belongs in each section
- ONLY update the actual content that appears BELOW the italic _section descriptions_ within each existing section
- Do NOT add any new sections, summaries, or information outside the existing structure
- Do not reference this note-taking process or instructions anywhere in the notes
- It's OK to skip updating a section if there are no substantial new insights to add. Do not add filler content like "No info yet", just leave sections blank/unedited if appropriate.
- Write DETAILED, INFO-DENSE content for each section - include specifics like file paths, function names, error messages, exact commands, technical details, etc.
- For "Key results", include the complete, exact output the user requested (e.g., full table, full answer, etc.)
- Do not include information that's already in the CLAUDE.md files included in the context
- Keep each section under ~2000 tokens/words - if a section is approaching this limit, condense it by cycling out less important details while preserving the most important information
- Focus on actionable, specific information that would help someone understand or recreate the work discussed in the conversation
- IMPORTANT: Always update "Current State" to reflect the most recent work - this is critical for continuity after compaction

STRUCTURE PRESERVATION REMINDER:
Each section has TWO parts that must be preserved exactly as they appear in the current file:
1. The section header (line starting with #)
2. The italic description line (the _italicized text_ immediately after the header - this is a template instruction)

You ONLY update the actual content that comes AFTER these two preserved lines. The italic description lines starting and ending with underscores are part of the template structure, NOT content to be edited or removed.

REMEMBER: Use the Edit tool in parallel and stop. Do not continue after the edits. Only include insights from the actual user conversation, never from these note-taking instructions. Do not delete or change section headers or italic _section descriptions_."""
