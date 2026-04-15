"""ConfigDialog — Configuration dialog.

Re-implements configuration editing dialogs.
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from textual.app import ComposeResult

from textual.widgets import Input

from py_claw.ui.widgets.dialog import Dialog, ExitState
from py_claw.ui.widgets.themed_text import ThemedText


class ConfigDialog(Dialog):
    """Configuration editor dialog.

    Allows editing various configuration options.
    """

    def __init__(
        self,
        config: dict,
        on_save: Callable[[dict], None] | None = None,
        on_cancel: Callable[[], None] | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        self._config = config
        self._on_save = on_save
        self._on_cancel = on_cancel
        super().__init__(
            title="Configuration",
            confirm_label="Save",
            deny_label="Cancel",
            id=id,
            classes=classes,
        )

    def compose(self) -> ComposeResult:
        """Compose the config editor."""
        # Model selection
        yield ThemedText("Model:", variant="normal")
        yield Input(
            value=self._config.get("model", "claude-sonnet-4-20250514"),
            placeholder="claude-sonnet-4-20250514",
            id="config-model-input",
        )

        # API base URL
        yield ThemedText("API Base URL:", variant="normal")
        yield Input(
            value=self._config.get("apiBaseUrl", ""),
            placeholder="https://api.anthropic.com",
            id="config-api-url-input",
        )

        # Max tokens
        yield ThemedText("Max Tokens:", variant="normal")
        yield Input(
            value=str(self._config.get("maxTokens", 8192)),
            placeholder="8192",
            id="config-max-tokens-input",
        )

        # Temperature
        yield ThemedText("Temperature:", variant="normal")
        yield Input(
            value=str(self._config.get("temperature", 1.0)),
            placeholder="1.0",
            id="config-temp-input",
        )

    def confirm(self) -> None:
        """Handle save."""
        model_input = self.query_one("#config-model-input", Input)
        api_url_input = self.query_one("#config-api-url-input", Input)
        max_tokens_input = self.query_one("#config-max-tokens-input", Input)
        temp_input = self.query_one("#config-temp-input", Input)

        config_data = {
            "model": model_input.value,
            "apiBaseUrl": api_url_input.value,
            "maxTokens": int(max_tokens_input.value) if max_tokens_input.value else 8192,
            "temperature": float(temp_input.value) if temp_input.value else 1.0,
        }

        if self._on_save:
            self._on_save(config_data)
