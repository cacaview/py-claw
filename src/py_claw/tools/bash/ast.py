"""Bash AST node structures and traversal utilities.

Provides a tree-sitter compatible AST representation for bash commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class BashASTNode:
    """A node in a bash AST.

    Represents a parsed bash command structure with position information.
    The structure mirrors tree-sitter-bash AST output.
    """

    # Node type (e.g., 'command', 'word', 'pipe', 'redirect', etc.)
    type: str
    # Raw text content of this node
    text: str
    # UTF-8 byte offset of start position
    start_index: int
    # UTF-8 byte offset of end position
    end_index: int
    # Child nodes
    children: list[BashASTNode] = field(default_factory=list)

    @property
    def child_count(self) -> int:
        """Number of child nodes."""
        return len(self.children)

    def is_named(self) -> bool:
        """Whether this is a named node (not a trivial token)."""
        # Named nodes typically have meaningful types
        trivial_types = {
            "WORD",
            "NEWLINE",
            "COMMENT",
            "EOF",
            "OP",
            "NUMBER",
        }
        return self.type not in trivial_types

    def get_child(self, type: str) -> BashASTNode | None:
        """Get first child of given type."""
        for child in self.children:
            if child.type == type:
                return child
        return None

    def get_children(self, type: str) -> list[BashASTNode]:
        """Get all children of given type."""
        return [child for child in self.children if child.type == type]

    def find_all(self, type: str) -> Iterator[BashASTNode]:
        """Recursively find all nodes of given type."""
        if self.type == type:
            yield self
        for child in self.children:
            yield from child.find_all(type)

    def find_first(self, type: str) -> BashASTNode | None:
        """Recursively find first node of given type."""
        if self.type == type:
            return self
        for child in self.children:
            result = child.find_first(type)
            if result is not None:
                return result
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "type": self.type,
            "text": self.text,
            "startIndex": self.start_index,
            "endIndex": self.end_index,
            "children": [child.to_dict() for child in self.children],
        }


def walk_ast(node: BashASTNode) -> Iterator[BashASTNode]:
    """Walk AST in depth-first order.

    Args:
        node: Root node to walk

    Yields:
        Each node in the AST
    """
    yield node
    for child in node.children:
        yield from walk_ast(child)


def count_nodes(node: BashASTNode) -> int:
    """Count total nodes in AST.

    Args:
        node: Root node

    Returns:
        Total node count including root
    """
    return 1 + sum(count_nodes(child) for child in node.children)


def get_command_name(node: BashASTNode) -> str | None:
    """Extract command name from a command node.

    Args:
        node: A 'command' type node (or a 'program' node to search within)

    Returns:
        Command name string, or None if not found
    """
    # If this is a command node, find the first WORD child (possibly nested in simple_command)
    if node.type == "command":
        for child in node.children:
            if child.type == "WORD":
                return child.text
            # WORDs may be inside simple_command
            if child.type == "simple_command":
                for sc_child in child.children:
                    if sc_child.type == "WORD":
                        return sc_child.text
        return None
    # Recurse into children for program/command_list nodes
    for child in node.children:
        result = get_command_name(child)
        if result is not None:
            return result
    return None


def get_words(node: BashASTNode) -> list[str]:
    """Get all word nodes' text content.

    Args:
        node: Root node to search

    Returns:
        List of word contents
    """
    words = []
    for word_node in node.find_all("WORD"):
        words.append(word_node.text)
    return words


def has_compound_operators(node: BashASTNode) -> bool:
    """Check if command has compound operators (&&, ||, ;).

    Compound operators split a command into multiple command_list siblings.

    Args:
        node: Root node

    Returns:
        True if compound operators found
    """
    import re

    # Check node text if non-empty
    if node.text:
        return bool(re.search(r"&&|\|\||;", node.text))

    # Compound && and || produce multiple command_list children
    cmd_lists = node.get_children("command_list")
    if len(cmd_lists) > 1:
        return True

    # Recurse
    for child in node.children:
        if has_compound_operators(child):
            return True
    return False


def has_pipeline(node: BashASTNode) -> bool:
    """Check if command has a pipeline (|).

    Args:
        node: Root node

    Returns:
        True if pipeline found
    """
    return node.find_first("pipe_sequence") is not None


def has_subshell(node: BashASTNode) -> bool:
    """Check if command has a subshell ((...) or $(...)).

    Args:
        node: Root node

    Returns:
        True if subshell found
    """
    # DOLLAR_PAREN nodes represent $(...) command substitution
    return node.find_first("DOLLAR_PAREN") is not None


def has_command_group(node: BashASTNode) -> bool:
    """Check if command has a command group ({...}).

    Args:
        node: Root node

    Returns:
        True if command group found
    """
    # Look for '{' and '}' WORD tokens in sequence
    words = [n.text for n in node.find_all("WORD")]
    return "{" in words and "}" in words


def has_redirect(node: BashASTNode) -> bool:
    """Check if command has file redirect operators (> , >>, <).

    Args:
        node: Root node

    Returns:
        True if redirect found
    """
    return node.find_first("redirect") is not None


def get_redirects(node: BashASTNode) -> list[str]:
    """Get all redirect operator texts from a command.

    Args:
        node: Root node

    Returns:
        List of redirect texts (e.g., ['> /tmp/out.txt'])
    """
    return [r.text for r in node.find_all("redirect")]
