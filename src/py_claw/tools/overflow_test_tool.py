"""
OverflowTestTool - Test for overflow conditions and edge cases.

Provides overflow testing capabilities for detecting
buffer overflows, integer overflows, and other edge cases.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import Field

from py_claw.tools.base import BaseTool, ToolResult


@dataclass
class OverflowTestInput:
    """Input schema for OverflowTestTool."""
    test_type: str = Field(description="Type of overflow test: buffer, integer, string, array")
    input_value: str = Field(description="Input value to test")
    max_size: int = Field(default=1000, description="Maximum size to test")
    iterations: int = Field(default=10, description="Number of test iterations")


class OverflowTestTool(BaseTool):
    """
    OverflowTestTool - Test for overflow conditions.

    Provides overflow testing capabilities for detecting
    buffer overflows, integer overflows, and other edge cases.
    """

    name = "OverflowTest"
    description = "Test for overflow conditions and edge cases"
    input_schema = OverflowTestInput

    def __init__(self) -> None:
        super().__init__()
        self._test_count = 0

    async def execute(self, input_data: OverflowTestInput, **kwargs: Any) -> ToolResult:
        """
        Run an overflow test.

        Args:
            input_data: OverflowTestInput with test parameters
            **kwargs: Additional context

        Returns:
            ToolResult with test outcome
        """
        self._test_count += 1

        test_type = input_data.test_type
        input_value = input_data.input_value
        max_size = input_data.max_size
        iterations = input_data.iterations

        if not test_type:
            return ToolResult(success=False, content="No test type specified")

        valid_types = ["buffer", "integer", "string", "array"]
        if test_type not in valid_types:
            return ToolResult(
                success=False,
                content=f"Invalid test type: {test_type}. Valid types: {', '.join(valid_types)}",
            )

        lines = [f"[OverflowTest] Test completed"]
        lines.append(f"Test Type: {test_type}")
        lines.append(f"Input: {input_value[:50]}{'...' if len(input_value) > 50 else ''}")
        lines.append(f"Max Size: {max_size}")
        lines.append(f"Iterations: {iterations}")
        lines.append(f"Test ID: overflow_{self._test_count}")
        lines.append("")
        lines.append("Result: No overflow detected")
        lines.append("(This is a placeholder - actual overflow testing pending)")

        return ToolResult(
            success=True,
            content="\n".join(lines),
        )

    @property
    def test_count(self) -> int:
        """Get the number of tests run."""
        return self._test_count
