"""Debug logging utilities (mirrors TypeScript src/utils/log.ts).

Note: This module is named 'debug' to match the TypeScript source file name.
The actual functionality is debug logging (log.ts in TypeScript).

Provides:
- Debug log level management
- Debug mode detection
- Debug message filtering and writing
"""

from py_claw.services.log.log import (
    DebugLogLevel,
    enable_debug_logging,
    flush_debug_logs,
    get_debug_file_path,
    get_debug_filter,
    get_debug_log_path,
    get_has_formatted_output,
    get_min_debug_log_level,
    is_debug_mode,
    is_debug_to_stderr,
    log_ant_error,
    log_for_debugging,
    set_has_formatted_output,
    should_log_debug_message,
)

__all__ = [
    "DebugLogLevel",
    "enable_debug_logging",
    "flush_debug_logs",
    "get_debug_file_path",
    "get_debug_filter",
    "get_debug_log_path",
    "get_has_formatted_output",
    "get_min_debug_log_level",
    "is_debug_mode",
    "is_debug_to_stderr",
    "log_ant_error",
    "log_for_debugging",
    "set_has_formatted_output",
    "should_log_debug_message",
]
