"""Keyword detection for voice input.

Provides utilities for detecting keywords and phrases
in transcribed text.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def detect_keywords(
    text: str,
    keywords: list[str],
    case_sensitive: bool = False,
) -> list[str]:
    """Detect keywords in text.

    Args:
        text: Input text to search.
        keywords: List of keywords to look for.
        case_sensitive: Whether to match case-sensitively.

    Returns:
        List of detected keywords (in order of appearance in text).
    """
    if not text or not keywords:
        return []

    detected: list[str] = []
    text_to_search = text if case_sensitive else text.lower()

    for keyword in keywords:
        pattern = re.escape(keyword if case_sensitive else keyword.lower())
        if re.search(pattern, text_to_search):
            if keyword not in detected:
                detected.append(keyword)

    return detected


def detect_phrase_matches(
    text: str,
    phrases: list[str],
    partial: bool = True,
) -> list[tuple[str, int, int]]:
    """Detect phrase matches with positions.

    Args:
        text: Input text to search.
        phrases: List of phrases to look for.
        partial: Whether to allow partial matches.

    Returns:
        List of (phrase, start_pos, end_pos) tuples.
    """
    if not text or not phrases:
        return []

    matches: list[tuple[str, int, int]] = []
    text_lower = text.lower()

    for phrase in phrases:
        phrase_lower = phrase.lower()
        if partial:
            # Look for phrase as substring
            start = 0
            while True:
                pos = text_lower.find(phrase_lower, start)
                if pos == -1:
                    break
                matches.append((phrase, pos, pos + len(phrase)))
                start = pos + 1
        else:
            # Word boundary match
            pattern = r'\b' + re.escape(phrase_lower) + r'\b'
            for match in re.finditer(pattern, text_lower):
                matches.append((phrase, match.start(), match.end()))

    # Sort by position
    matches.sort(key=lambda x: x[1])
    return matches


def extract_keyword_context(
    text: str,
    keyword: str,
    context_words: int = 3,
) -> str:
    """Extract context around a keyword.

    Args:
        text: Input text.
        keyword: Keyword to find.
        context_words: Number of words to include before/after.

    Returns:
        Text snippet with keyword and surrounding context.
    """
    words = text.split()
    keyword_lower = keyword.lower()

    for i, word in enumerate(words):
        if keyword_lower in word.lower():
            start = max(0, i - context_words)
            end = min(len(words), i + context_words + 1)
            return " ".join(words[start:end])

    return ""


def build_keyword_pattern(
    keywords: list[str],
    word_boundary: bool = True,
) -> str:
    """Build a regex pattern for multiple keywords.

    Args:
        keywords: List of keywords.
        word_boundary: Whether to require word boundaries.

    Returns:
        Regex pattern string.
    """
    if not keywords:
        return ""

    escaped = [re.escape(k) for k in keywords]
    pattern = "|".join(escaped)

    if word_boundary:
        pattern = r"\b(" + pattern + r")\b"

    return pattern


class KeywordDetector:
    """Stateful keyword detector.

    Tracks keyword occurrences and can detect
    new or repeated keywords.
    """

    def __init__(self, keywords: list[str]) -> None:
        """Initialize keyword detector.

        Args:
            keywords: List of keywords to track.
        """
        self._keywords = keywords
        self._seen: set[str] = set()
        self._pattern = re.compile(
            build_keyword_pattern(keywords),
            re.IGNORECASE,
        )

    def detect(self, text: str) -> list[str]:
        """Detect keywords in text.

        Args:
            text: Input text.

        Returns:
            List of detected keywords.
        """
        if not text:
            return []

        matches = re.findall(self._pattern, text)
        return list(set(matches))

    def detect_new(self, text: str) -> list[str]:
        """Detect new (not previously seen) keywords.

        Args:
            text: Input text.

        Returns:
            List of newly detected keywords.
        """
        detected = self.detect(text)
        new = [k for k in detected if k not in self._seen]

        # Mark as seen
        for k in detected:
            self._seen.add(k)

        return new

    def add_keyword(self, keyword: str) -> None:
        """Add a new keyword to track.

        Args:
            keyword: Keyword to add.
        """
        if keyword not in self._keywords:
            self._keywords.append(keyword)
            # Rebuild pattern
            self._pattern = re.compile(
                build_keyword_pattern(self._keywords),
                re.IGNORECASE,
            )

    def remove_keyword(self, keyword: str) -> None:
        """Remove a keyword from tracking.

        Args:
            keyword: Keyword to remove.
        """
        if keyword in self._keywords:
            self._keywords.remove(keyword)
            # Rebuild pattern
            if self._keywords:
                self._pattern = re.compile(
                    build_keyword_pattern(self._keywords),
                    re.IGNORECASE,
                )
            else:
                self._pattern = re.compile("(?!)")  # Never matches

    def reset(self) -> None:
        """Reset seen keywords."""
        self._seen.clear()

    @property
    def keywords(self) -> list[str]:
        """Get current keywords."""
        return list(self._keywords)
