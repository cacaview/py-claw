"""Prompt suggestion UX integration tests for REPLScreen/PromptFooter."""

from __future__ import annotations

import pytest

from textual.widgets import Static

from tests.test_tui.conftest import apply_compact_layout, type_text

pytestmark = pytest.mark.asyncio


def _footer_text(screen) -> str:
    footer = screen.query_one("#repl-footer")
    texts: list[str] = []
    for child in footer.query(Static):
        renderable = getattr(child, "renderable", None)
        if renderable is None:
            if hasattr(child, "render"):
                renderable = child.render()
        text = str(renderable)
        if text.strip() and text.strip() != "None":
            texts.append(text)
    return "\n".join(texts)


class TestPromptSuggestionFooter:
    async def test_slash_suggestions_render_only_in_footer(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        prompt = screen.query_one("#repl-prompt-input")
        footer = screen.query_one("#repl-footer")

        assert len(prompt.suggestion_items) > 0
        assert footer.has_suggestions is True
        assert list(prompt.query("#pi-suggestion-list").results()) == []

    async def test_footer_suggestion_list_does_not_expand_into_blank_gap(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        footer = screen.query_one("#repl-footer")
        suggestion_list = footer.query_one("#pf-suggestion-list")

        assert footer.region.height < 16
        assert suggestion_list.region.height <= 10

    async def test_tab_accepts_best_command_suggestion(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "/he")
        await pilot.pause()
        await pilot.press("tab")
        await pilot.pause()

        assert screen.get_prompt_value() == "/help "
        footer = screen.query_one("#repl-footer")
        prompt = screen.query_one("#repl-prompt-input")
        print(f"SUGGESTIONS: {[(x.display_text, getattr(x, 'type', None)) for x in prompt.suggestion_items]}")
        assert footer.has_suggestions is False

    async def test_up_down_navigation_updates_footer_selection(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        footer = screen.query_one("#repl-footer")
        assert footer.selected_index == -1

        await pilot.press("down")
        await pilot.pause()
        assert footer.selected_index == 0

        await pilot.press("down")
        await pilot.pause()
        assert footer.selected_index == 1

        await pilot.press("up")
        await pilot.pause()
        assert footer.selected_index == 0

    async def test_pageup_stops_at_first_item(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        footer = screen.query_one("#repl-footer")
        await pilot.press("pagedown")
        await pilot.pause()
        moved_index = footer.selected_index
        assert moved_index >= 0

        await pilot.press("pageup")
        await pilot.pause()
        assert footer.selected_index == 0

        await pilot.press("pageup")
        await pilot.pause()
        assert footer.selected_index == 0

    async def test_escape_clears_visible_suggestions(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        footer = screen.query_one("#repl-footer")
        assert footer.has_suggestions is True

        await pilot.press("escape")
        await pilot.pause()
        assert footer.has_suggestions is False

    async def test_bare_channel_input_shows_channel_suggestions(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "#")
        await pilot.pause()

        footer_text = _footer_text(screen)
        footer = screen.query_one("#repl-footer")
        sug_vert = footer.query_one("#pf-suggestion-vertical")
        print(f"\nCHANNEL HAS_SUGGESTIONS={footer.has_suggestions}")
        print(f"CHANNEL CHILDREN: {len(sug_vert.children)}")
        for i, child in enumerate(sug_vert.children):
            print(f"CHILD {i}: {getattr(child, 'renderable', None)}")
        print(f"CHANNEL FOOTER: {repr(footer_text)}")
        assert "general" in footer_text.lower() or "channel" in footer_text.lower()

    async def test_bare_agent_input_uses_agent_suggestion_mode(self, pilot, screen):
        prompt = screen.query_one("#repl-prompt-input")
        screen._engine.set_team_context(  # noqa: SLF001
            teammates={"alice": {"color": "blue", "agent_type": "coder"}},
            agent_names={},
        )
        screen.focus_prompt()
        await type_text(pilot, "@")
        await pilot.pause()

        assert len(prompt.suggestion_items) >= 1
        footer = screen.query_one("#repl-footer")
        print(f"\nAGENT has_suggestions={footer.has_suggestions}")
        footer_text = _footer_text(screen)
        print(f"\nAGENT FOOTER: {repr(footer_text)}")
        assert "alice" in footer_text.lower()

    async def test_mid_input_slash_keeps_footer_suggestions(self, pilot, screen):
        screen.focus_prompt()
        await type_text(pilot, "fix /he")
        await pilot.pause()

        prompt = screen.query_one("#repl-prompt-input")
        footer = screen.query_one("#repl-footer")
        assert len(prompt.suggestion_items) >= 1
        assert footer.has_suggestions is True

    async def test_narrow_layout_keeps_suggestions_visible(self, pilot, screen):
        apply_compact_layout(pilot.app, (79, 28))
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        footer = screen.query_one("#repl-footer")
        footer_text = _footer_text(screen)
        assert footer.compact_mode == "narrow"
        assert footer.has_suggestions is True
        assert "navigate" in footer_text.lower() or "tab" in footer_text.lower()

    async def test_tight_layout_keeps_minimal_suggestion_feedback(self, pilot, screen):
        apply_compact_layout(pilot.app, (79, 19))
        screen.focus_prompt()
        await type_text(pilot, "/")
        await pilot.pause()

        footer = screen.query_one("#repl-footer")
        footer_text = _footer_text(screen)
        assert footer.compact_mode == "tight"
        assert footer.has_suggestions is True
        assert "tab" in footer_text.lower() or "↑↓" in footer_text
