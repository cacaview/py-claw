"""Fork subprocess module for isolated agent execution."""

from __future__ import annotations

from py_claw.fork.backend import ForkedAgentBackend
from py_claw.fork.child_main import _main
from py_claw.fork.process import ForkedAgentProcess
from py_claw.fork.protocol import (
    ForkErrorMessage,
    ForkHistoryMessage,
    ForkInitMessage,
    ForkMessage,
    ForkOutputMessage,
    ForkResultMessage,
    ForkStopMessage,
    ForkTurnMessage,
    NDJSONParser,
    build_fork_boilerplate,
)

__all__ = [
    "ForkedAgentBackend",
    "ForkedAgentProcess",
    "ForkMessage",
    "ForkInitMessage",
    "ForkTurnMessage",
    "ForkStopMessage",
    "ForkOutputMessage",
    "ForkResultMessage",
    "ForkErrorMessage",
    "NDJSONParser",
    "build_fork_boilerplate",
]
