"""
ANSI to SVG conversion utilities.

Converts ANSI-colored terminal output to SVG format for
display in web contexts or documentation.

Reference: ClaudeCode-main/src/utils/ansiToSvg.ts
"""
from __future__ import annotations

import re
import html
from dataclasses import dataclass
from typing import Callable


@dataclass
class AnsiStyle:
    """Parsed ANSI style attributes."""
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    foreground: str | None = None
    background: str | None = None


# ANSI color code to hex mapping
ANSI_COLORS_256 = {
    # Standard colors (0-15)
    0: "#000000",   # black
    1: "#cc0000",   # red
    2: "#4e9a06",   # green
    3: "#c4a000",   # yellow
    4: "#3465a4",   # blue
    5: "#75507b",   # magenta
    6: "#06989a",   # cyan
    7: "#d3d7cf",   # white
    8: "#555753",   # bright black
    9: "#ef2929",   # bright red
    10: "#8ae234",  # bright green
    11: "#fce94f",  # bright yellow
    12: "#729fcf",  # bright blue
    13: "#ad7fa8",  # bright magenta
    14: "#34e2e2",  # bright cyan
    15: "#ffffff",  # bright white
}

# Fill in extended 256 colors with approximate values
for i in range(16, 256):
    if i < 232:
        # 216 color cube (6x6x6)
        r = ((i - 16) // 36) * 51
        g = ((i - 16) // 6) % 6 * 51
        b = (i - 16) % 6 * 51
        ANSI_COLORS_256[i] = f"#{r:02x}{g:02x}{b:02x}"
    else:
        # 24 grayscale
        gray = (i - 232) * 10 + 8
        ANSI_COLORS_256[i] = f"#{gray:02x}{gray:02x}{gray:02x}"


def ansi_to_svg(
    text: str,
    *,
    font_family: str = "monospace",
    font_size: int = 14,
    line_height: float = 1.2,
    background: str = "transparent",
    width: int | None = None,
    padding: int = 10,
) -> str:
    """
    Convert ANSI-colored text to SVG.

    Args:
        text: Text with ANSI escape codes
        font_family: CSS font-family for text
        font_size: Font size in pixels
        line_height: Line height multiplier
        background: Background color (CSS color or "transparent")
        width: Fixed width in pixels, or None for auto
        padding: Padding around content in pixels

    Returns:
        SVG string representation of the text
    """
    segments = _parse_ansi(text)
    lines = _group_into_lines(segments)

    if not lines:
        return _empty_svg(font_size, line_height, background, padding)

    # Calculate dimensions
    char_width = font_size * 0.6  # Approximate monospace char width
    max_line_length = max(
        sum(len(seg.text) for seg in line.segments) for line in lines
    )
    text_width = max_line_length * char_width
    text_height = len(lines) * font_size * line_height

    svg_width = (width or text_width) + 2 * padding
    svg_height = text_height + 2 * padding

    # Build SVG
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{svg_width}" height="{svg_height}">',
    ]

    # Background
    if background != "transparent":
        svg_parts.append(
            f'<rect width="100%" height="100%" fill="{background}"/>'
        )

    # Style definitions
    svg_parts.append(
        f'<style>'
        f'.text {{ font-family: {font_family}; font-size: {font_size}px; }}'
        f'</style>'
    )

    # Content group with padding
    svg_parts.append(f'<g transform="translate({padding}, {padding})">')

    y = font_size  # Start baseline at font_size

    for line in lines:
        x = 0
        for segment in line.segments:
            style = _build_css_style(segment.style)
            escaped_text = html.escape(segment.text)
            # Preserve spaces with XML entity
            escaped_text = escaped_text.replace(" ", "&#160;")

            if style:
                svg_parts.append(
                    f'<text x="{x}" y="{y}" {style} class="text">'
                    f'{escaped_text}</text>'
                )
            else:
                svg_parts.append(
                    f'<text x="{x}" y="{y}" class="text">{escaped_text}</text>'
                )
            x += len(segment.text) * char_width

        y += font_size * line_height

    svg_parts.append("</g>")
    svg_parts.append("</svg>")

    return "".join(svg_parts)


@dataclass
class TextSegment:
    """A segment of text with a specific style."""
    text: str
    style: AnsiStyle


@dataclass
class TextLine:
    """A line of text composed of segments."""
    segments: list[TextSegment]


def _parse_ansi(text: str) -> list[TextSegment]:
    """Parse ANSI escape sequences into styled segments."""
    segments = []
    current_style = AnsiStyle()
    current_text = []

    # ANSI escape sequence regex
    ansi_pattern = re.compile(r"\033\[([0-9;]*)m")

    i = 0
    while i < len(text):
        match = ansi_pattern.search(text, i)
        if not match:
            # Rest of the text
            if text[i:]:
                current_text.append(text[i:])
            break

        # Text before the escape
        if match.start() > i:
            current_text.append(text[i:match.start()])

        # Parse escape sequence
        codes = match.group(1).split(";") if match.group(1) else []
        if not codes or codes == ["0"]:
            # Reset
            if current_text:
                segments.append(TextSegment(
                    text="".join(current_text),
                    style=AnsiStyle(**current_style.__dict__)
                ))
                current_text = []
            current_style = AnsiStyle()
        else:
            for code in codes:
                code = code.strip()
                if not code:
                    continue
                code_int = int(code) if code.isdigit() else 0

                if code_int == 1:
                    current_style.bold = True
                elif code_int == 2:
                    current_style.dim = True
                elif code_int == 3:
                    current_style.italic = True
                elif code_int == 4:
                    current_style.underline = True
                elif code_int == 30:
                    current_style.foreground = ANSI_COLORS_256.get(0, "#000000")
                elif code_int == 31:
                    current_style.foreground = ANSI_COLORS_256.get(1, "#cc0000")
                elif code_int == 32:
                    current_style.foreground = ANSI_COLORS_256.get(2, "#4e9a06")
                elif code_int == 33:
                    current_style.foreground = ANSI_COLORS_256.get(3, "#c4a000")
                elif code_int == 34:
                    current_style.foreground = ANSI_COLORS_256.get(4, "#3465a4")
                elif code_int == 35:
                    current_style.foreground = ANSI_COLORS_256.get(5, "#75507b")
                elif code_int == 36:
                    current_style.foreground = ANSI_COLORS_256.get(6, "#06989a")
                elif code_int == 37:
                    current_style.foreground = ANSI_COLORS_256.get(7, "#d3d7cf")
                elif code_int == 39:
                    current_style.foreground = None
                elif code_int == 40:
                    current_style.background = ANSI_COLORS_256.get(0, "#000000")
                elif code_int == 41:
                    current_style.background = ANSI_COLORS_256.get(1, "#cc0000")
                elif code_int == 42:
                    current_style.background = ANSI_COLORS_256.get(2, "#4e9a06")
                elif code_int == 43:
                    current_style.background = ANSI_COLORS_256.get(3, "#c4a000")
                elif code_int == 44:
                    current_style.background = ANSI_COLORS_256.get(4, "#3465a4")
                elif code_int == 45:
                    current_style.background = ANSI_COLORS_256.get(5, "#75507b")
                elif code_int == 46:
                    current_style.background = ANSI_COLORS_256.get(6, "#06989a")
                elif code_int == 47:
                    current_style.background = ANSI_COLORS_256.get(7, "#d3d7cf")
                elif code_int == 49:
                    current_style.background = None
                elif code_int >= 90 and code_int <= 97:
                    # Bright foreground colors
                    current_style.foreground = ANSI_COLORS_256.get(code_int - 90 + 8)
                elif code_int >= 100 and code_int <= 107:
                    # Bright background colors
                    current_style.background = ANSI_COLORS_256.get(code_int - 100 + 8)
                elif code_int == 38 or code_int == 48:
                    # Extended colors (256-color or RGB)
                    pass  # Simplified handling

        i = match.end()

    # Flush remaining text
    if current_text:
        segments.append(TextSegment(
            text="".join(current_text),
            style=AnsiStyle(**current_style.__dict__)
        ))

    return segments


def _group_into_lines(segments: list[TextSegment]) -> list[TextLine]:
    """Group segments into lines based on newlines."""
    lines = []
    current_line = []

    for segment in segments:
        parts = segment.text.split("\n")
        for j, part in enumerate(parts):
            if j > 0:
                # Newline - save current line and start new one
                if current_line:
                    lines.append(TextLine(segments=current_line))
                    current_line = []
            if part:
                current_line.append(TextSegment(
                    text=part,
                    style=AnsiStyle(**segment.style.__dict__)
                ))

    if current_line:
        lines.append(TextLine(segments=current_line))

    return lines


def _build_css_style(style: AnsiStyle) -> str:
    """Build SVG style attributes from AnsiStyle."""
    attrs = []

    if style.bold:
        attrs.append("font-weight: bold")
    if style.dim:
        attrs.append("opacity: 0.7")
    if style.italic:
        attrs.append("font-style: italic")
    if style.underline:
        attrs.append("text-decoration: underline")

    if style.foreground:
        attrs.append(f'fill="{style.foreground}"')

    if style.background:
        attrs.append(f'stroke="{style.background}"')

    if not attrs:
        return ""

    # Build SVG attribute string
    result_parts = []
    for attr in attrs:
        if ":" in attr:
            key, value = attr.split(":", 1)
            result_parts.append(f'{key.strip()}="{value.strip()}"')
        else:
            result_parts.append(attr)
    return " ".join(result_parts)


def _empty_svg(
    font_size: int,
    line_height: float,
    background: str,
    padding: int,
) -> str:
    """Return an empty SVG for empty input."""
    height = font_size * line_height + 2 * padding
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100" height="{height}">',
    ]
    if background != "transparent":
        svg_parts.append(
            f'<rect width="100%" height="100%" fill="{background}"/>'
        )
    svg_parts.append("</svg>")
    return "".join(svg_parts)
