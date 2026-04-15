"""Voice tool for audio capture and transcription."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field

from py_claw.schemas.common import PyClawBaseModel
from py_claw.tools.base import ToolDefinition, ToolError, ToolPermissionTarget

if TYPE_CHECKING:
    pass


class VoiceToolInput(PyClawBaseModel):
    """Input for Voice tool."""

    action: str = Field(
        description="Action to perform: 'start', 'stop', 'status', 'list-devices'"
    )
    device: int | None = Field(
        default=None,
        description="Audio device index (for 'start' action). Use 'list-devices' to see available.",
    )
    keywords: list[str] | None = Field(
        default=None,
        description="Keywords to detect in speech (for 'start' action).",
    )
    sample_rate: int | None = Field(
        default=None,
        description="Audio sample rate in Hz (for 'start' action). Default: 16000.",
    )
    language: str | None = Field(
        default=None,
        description="Language code for transcription (for 'start' action). Default: en-US.",
    )


class VoiceToolResult(PyClawBaseModel):
    """Result from Voice tool."""

    success: bool = True
    action: str
    message: str
    devices: list[dict] | None = None
    is_active: bool | None = None


class VoiceTool:
    """Tool for voice input and transcription.

    Provides audio capture from microphone with real-time
    transcription using STT services.
    """

    definition = ToolDefinition(name="Voice", input_model=VoiceToolInput)

    def permission_target(self, payload: dict[str, object]) -> ToolPermissionTarget:
        """Get permission target for voice tool.

        Args:
            payload: Tool input payload.

        Returns:
            Permission target.
        """
        return ToolPermissionTarget(
            tool_name=self.definition.name,
            content=None,  # Voice doesn't expose file paths
        )

    def execute(self, arguments: VoiceToolInput, *, cwd: str) -> dict[str, object]:
        """Execute voice tool action.

        Args:
            arguments: Tool input arguments.
            cwd: Current working directory.

        Returns:
            Tool execution result.

        Raises:
            ToolError: If voice operation fails.
        """
        action = arguments.action.lower()

        try:
            from py_claw.services.voice import (
                VoiceError,
                VoiceService,
                get_voice_service,
                list_audio_devices,
            )

            if action == "list-devices":
                return self._list_devices()

            elif action == "start":
                return self._start(arguments)

            elif action == "stop":
                return self._stop()

            elif action == "status":
                return self._status()

            else:
                raise ToolError(f"Unknown voice action: {action}. Use: start, stop, status, list-devices")

        except VoiceError as e:
            raise ToolError(f"Voice error: {e}") from e

    def _list_devices(self) -> dict[str, object]:
        """List available audio devices."""
        from py_claw.services.voice import list_audio_devices

        devices = list_audio_devices()
        device_list = [
            {
                "index": d.index,
                "name": d.name,
                "input_channels": d.max_input_channels,
                "sample_rate": d.default_sample_rate,
            }
            for d in devices
        ]

        return VoiceToolResult(
            success=True,
            action="list-devices",
            message=f"Found {len(devices)} audio device(s)",
            devices=device_list,
        ).model_dump()

    def _start(self, arguments: VoiceToolInput) -> dict[str, object]:
        """Start voice capture."""
        from py_claw.services.voice import VoiceConfig, VoiceService, get_voice_service

        # Get or create service
        service = get_voice_service()

        if service.is_active:
            return VoiceToolResult(
                success=True,
                action="start",
                message="Voice capture is already active",
                is_active=True,
            ).model_dump()

        # Configure service
        config = VoiceConfig.from_env()
        if arguments.sample_rate:
            config.sample_rate = arguments.sample_rate
        if arguments.language:
            config.language = arguments.language
        if arguments.keywords:
            config.keywords = arguments.keywords

        service._config = config
        service._audio_device_index = arguments.device

        # Start capture (sync wrapper for tool)
        import asyncio

        async def do_start() -> None:
            await service.start()

        try:
            asyncio.get_event_loop().run_until_complete(do_start())
        except RuntimeError as e:
            raise ToolError(f"Failed to start voice: {e}") from e

        return VoiceToolResult(
            success=True,
            action="start",
            message="Voice capture started",
            is_active=True,
        ).model_dump()

    def _stop(self) -> dict[str, object]:
        """Stop voice capture."""
        from py_claw.services.voice import get_voice_service

        service = get_voice_service()

        if not service.is_active:
            return VoiceToolResult(
                success=True,
                action="stop",
                message="Voice capture is not active",
                is_active=False,
            ).model_dump()

        import asyncio

        async def do_stop() -> None:
            await service.stop()

        try:
            asyncio.get_event_loop().run_until_complete(do_stop())
        except RuntimeError as e:
            raise ToolError(f"Failed to stop voice: {e}") from e

        return VoiceToolResult(
            success=True,
            action="stop",
            message="Voice capture stopped",
            is_active=False,
        ).model_dump()

    def _status(self) -> dict[str, object]:
        """Get voice capture status."""
        from py_claw.services.voice import get_voice_service

        service = get_voice_service()

        return VoiceToolResult(
            success=True,
            action="status",
            message="Voice capture is " + ("active" if service.is_active else "inactive"),
            is_active=service.is_active,
        ).model_dump()
