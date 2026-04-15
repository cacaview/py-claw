"""
XML/HTML escaping utilities.

Provides functions for safely escaping special characters when
interpolating strings into XML/HTML content.

Reference: ClaudeCode-main/src/utils/xml.ts
"""
from __future__ import annotations


def escape_xml(s: str) -> str:
    """
    Escape XML/HTML special characters for safe interpolation into element
    text content (between tags).

    Use when untrusted strings (process stdout, user input, external data)
    go inside `<tag>${here}</tag>`.

    Args:
        s: String to escape

    Returns:
        Escaped string safe for XML text content
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_xml_attr(s: str) -> str:
    """
    Escape for interpolation into a double- or single-quoted attribute value.

    Escapes quotes in addition to & < >.

    Args:
        s: String to escape

    Returns:
        Escaped string safe for XML attribute values
    """
    return (
        escape_xml(s)
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )
