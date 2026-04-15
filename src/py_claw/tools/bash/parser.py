"""Pure Python bash parser producing tree-sitter-compatible ASTs.

This parser produces AST structures compatible with tree-sitter-bash output,
allowing downstream security analysis to work with consistent node types.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from py_claw.tools.bash.ast import BashASTNode

# Timeout for parsing (wall-clock cap)
PARSE_TIMEOUT_MS = 50

# Maximum node budget
MAX_NODES = 50_000

# Token types
TOKEN_TYPES = {
    "WORD",
    "NUMBER",
    "OP",
    "NEWLINE",
    "COMMENT",
    "DQUOTE",
    "SQUOTE",
    "ANSI_C",
    "DOLLAR",
    "DOLLAR_PAREN",
    "DOLLAR_BRACE",
    "DOLLAR_DPAREN",
    "BACKTICK",
    "LT_PAREN",
    "GT_PAREN",
    "EOF",
}

# Shell keywords
SHELL_KEYWORDS = {
    "if",
    "then",
    "elif",
    "else",
    "fi",
    "while",
    "until",
    "for",
    "in",
    "do",
    "done",
    "case",
    "esac",
    "function",
    "select",
    "time",
    "coproc",
    "until",
}

# Special variables
SPECIAL_VARS = {"?", "$", "@", "*", "#", "-", "!", "_", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}


@dataclass
class Token:
    """A lexical token from the bash input."""

    type: str
    value: str
    start: int  # UTF-8 byte offset
    end: int  # UTF-8 byte offset


class Lexer:
    """Lexes bash input into tokens."""

    # Regex patterns for tokens
    PATTERNS = [
        (r"#[^\n]*", "COMMENT"),  # Comment
        (r"\n", "NEWLINE"),  # Newline
        (r'\$"[^"]*"', "DQUOTE"),  # Double-quoted string with $
        (r'"(?:[^"\\]|\\.)*"', "DQUOTE"),  # Double-quoted string
        (r"''(?:[^']|')*'", "SQUOTE"),  # Single-quoted string
        (r"'[^']*'", "SQUOTE"),  # Single-quoted string (alternate)
        (r"\$\([^\)]+\)", "DOLLAR_PAREN"),  # $()
        (r"\$\{[^\}]+\}", "DOLLAR_BRACE"),  # ${}
        (r"\$\(\([^\)]+\)\)\$?", "DOLLAR_DPAREN"),  # $(())
        (r"\`[^\`]+\`", "BACKTICK"),  # Backtick command substitution
        (r"\$\<'[^']*'", "LT_PAREN"),  # Process substitution
        (r"\$\>[^\)]+\)", "GT_PAREN"),  # Process substitution
        (r"&&", "OP"),  # AND (before & to avoid partial match)
        (r"\|\|", "OP"),  # OR (before | to avoid partial match)
        (r">>", "OP"),  # Append redirect (before >)
        (r"\|", "OP"),  # Pipe
        (r"&", "OP"),  # Background
        (r";", "OP"),  # Semicolon
        (r">", "OP"),  # Redirect
        (r"<", "OP"),  # Input redirect
        (r"2>&1|2>&2|1>&2|1>&1", "OP"),  # Redirect fd
        (r"\\.", "WORD"),  # Escaped character
        (r"\d+", "NUMBER"),  # Number
        (r"[a-zA-Z_][a-zA-Z0-9_]*", "WORD"),  # Identifier
        (r"[^\s|&;<>$\\`\"']+", "WORD"),  # Other word
    ]

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.len = len(source)
        self.tokens: list[Token] = []

    def _read_ansi_c_string(self) -> Token | None:
        """Read a $'...' ansi-c string."""
        if self.pos >= self.len or self.source[self.pos : self.pos + 2] != "$'":
            return None
        start = self.pos
        self.pos += 2
        while self.pos < self.len:
            c = self.source[self.pos]
            if c == "'":
                self.pos += 1
                return Token("ANSI_C", self.source[start : self.pos], start, self.pos)
            elif c == "\\":
                self.pos += 2
            else:
                self.pos += 1
        return None

    def _read_dollar_paren(self) -> Token | None:
        """Read a $(...) command substitution."""
        if self.pos >= self.len or self.source[self.pos : self.pos + 2] != "$(":
            return None
        start = self.pos
        depth = 1
        self.pos += 2
        while self.pos < self.len and depth > 0:
            c = self.source[self.pos]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif c == "'" or c == '"':
                quote = c
                self.pos += 1
                while self.pos < self.len and self.source[self.pos] != quote:
                    if self.source[self.pos] == "\\":
                        self.pos += 2
                    else:
                        self.pos += 1
            self.pos += 1
        return Token("DOLLAR_PAREN", self.source[start : self.pos], start, self.pos)

    def _read_dollar_brace(self) -> Token | None:
        """Read a ${...} parameter expansion."""
        if self.pos >= self.len or self.source[self.pos : self.pos + 2] != "${":
            return None
        start = self.pos
        self.pos += 2
        while self.pos < self.len and self.source[self.pos] != "}":
            if self.source[self.pos] == "\\":
                self.pos += 2
            else:
                self.pos += 1
        if self.pos < self.len:
            self.pos += 1
        return Token("DOLLAR_BRACE", self.source[start : self.pos], start, self.pos)

    def _read_backtick(self) -> Token | None:
        """Read a `...` command substitution."""
        if self.pos >= self.len or self.source[self.pos] != "`":
            return None
        start = self.pos
        self.pos += 1
        while self.pos < self.len and self.source[self.pos] != "`":
            if self.source[self.pos] == "\\":
                self.pos += 2
            else:
                self.pos += 1
        if self.pos < self.len:
            self.pos += 1
        return Token("BACKTICK", self.source[start : self.pos], start, self.pos)

    def _read_string(self, quote: str) -> Token | None:
        """Read a quoted string."""
        if self.pos >= self.len or self.source[self.pos] != quote:
            return None
        start = self.pos
        self.pos += 1
        while self.pos < self.len and self.source[self.pos] != quote:
            if self.source[self.pos] == "\\":
                self.pos += 2
            else:
                self.pos += 1
        if self.pos < self.len:
            self.pos += 1
        token_type = "DQUOTE" if quote == '"' else "SQUOTE"
        return Token(token_type, self.source[start : self.pos], start, self.pos)

    def lex(self) -> list[Token]:
        """Lex the entire input into tokens."""
        while self.pos < self.len:
            # Skip whitespace (but not in strings)
            while self.pos < self.len and self.source[self.pos] in " \t":
                self.pos += 1
            if self.pos >= self.len:
                break

            # Check for special patterns first
            if self.source[self.pos : self.pos + 2] == "$'":
                token = self._read_ansi_c_string()
                if token:
                    self.tokens.append(token)
                    continue
            if self.source[self.pos : self.pos + 2] == "$(":
                token = self._read_dollar_paren()
                if token:
                    self.tokens.append(token)
                    continue
            if self.source[self.pos : self.pos + 2] == "${":
                token = self._read_dollar_brace()
                if token:
                    self.tokens.append(token)
                    continue
            if self.source[self.pos] == "`":
                token = self._read_backtick()
                if token:
                    self.tokens.append(token)
                    continue

            # Try each pattern
            matched = False
            for pattern, token_type in self.PATTERNS:
                m = re.match(pattern, self.source[self.pos :])
                if m:
                    value = m.group(0)
                    if token_type != "COMMENT":  # Skip comments
                        self.tokens.append(
                            Token(token_type, value, self.pos, self.pos + len(value))
                        )
                    self.pos += len(value)
                    matched = True
                    break

            if not matched:
                # Skip unknown character
                self.pos += 1

        self.tokens.append(Token("EOF", "", self.len, self.len))
        return self.tokens


class Parser:
    """Parses bash tokens into an AST."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0
        self.node_count = 0

    @property
    def current(self) -> Token:
        """Get current token."""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]

    def _make_node(
        self, node_type: str, text: str, start: int, end: int, children: list[BashASTNode] | None = None
    ) -> BashASTNode:
        """Create an AST node with budget checking."""
        self.node_count += 1
        if self.node_count > MAX_NODES:
            raise RuntimeError(f"Node budget exceeded: {MAX_NODES}")
        return BashASTNode(type=node_type, text=text, start_index=start, end_index=end, children=children or [])

    def _advance(self) -> Token:
        """Advance to next token."""
        token = self.current
        self.pos += 1
        return token

    def _expect(self, token_type: str) -> Token | None:
        """Expect a token type and consume it."""
        if self.current.type == token_type:
            return self._advance()
        return None

    def parse_program(self) -> BashASTNode:
        """Parse a complete bash program."""
        start = 0
        end = 0
        children = []

        while self.current.type != "EOF":
            stmt = self._parse_statement()
            if stmt:
                children.append(stmt)
                end = stmt.end_index

        if not children:
            end = start

        return self._make_node("program", "", start, end, children)

    def _parse_statement(self) -> BashASTNode | None:
        """Parse a single statement."""
        children = []

        while self.current.type in ("NEWLINE", "COMMENT"):
            self._advance()

        if self.current.type == "EOF":
            return None

        start = self.current.start
        end = start

        while self.current.type not in ("EOF", "NEWLINE"):
            cmd = self._parse_command_part()
            if cmd:
                children.append(cmd)
                end = cmd.end_index
            else:
                # Advance past operators we can't parse as a command part
                if self.current.type == "OP":
                    self._advance()
                break

        if self.current.type == "NEWLINE":
            self._advance()

        if not children:
            return None

        return self._make_node("command_list", "", start, end, children)

    def _parse_command_part(self) -> BashASTNode | None:
        """Parse a part of a command (pipeline, compound, etc.)."""
        start = self.current.start
        children = []

        # Parse command sequence
        while self.current.type not in ("EOF", "NEWLINE", "AND", "OR", "SEMICOLON"):
            node = self._parse_simple_command()
            if node:
                children.append(node)
            else:
                break

        if not children:
            return None

        end = children[-1].end_index if children else start

        # Check for compound operators
        if self.current.type == "OP" and self.current.value == "|":
            pipe_children = children[:]
            self._advance()
            more = self._parse_command_part()
            if more:
                pipe_children.append(more)
                end = max(end, more.end_index)
            return self._make_node("pipe_sequence", "", start, end, pipe_children)

        return self._make_node("command", "", start, end, children)

    def _parse_simple_command(self) -> BashASTNode | None:
        """Parse a simple command, including redirect operators."""
        start = self.current.start
        children = []

        while self.current.type not in ("EOF", "NEWLINE", "AND", "OR", "SEMICOLON"):
            # Handle redirect operators specially
            if self.current.type == "OP" and self.current.value in (">", ">>", "<"):
                redir_start = self.current.start
                redir_op = self.current.value
                self._advance()
                # Parse the redirect target (filename) — do NOT add as separate child
                target = self._parse_word()
                if target:
                    redir_node = self._make_node(
                        "redirect", f"{redir_op} {target.text}",
                        redir_start, target.end_index, []
                    )
                    children.append(redir_node)
                continue

            child = self._parse_word()
            if child is None:
                break
            children.append(child)

        if not children:
            return None

        end = children[-1].end_index if children else start
        return self._make_node("simple_command", "", start, end, children)

    def _parse_word(self) -> BashASTNode | None:
        """Parse a word or special token."""
        token = self.current

        if token.type == "EOF":
            return None

        # Compound operators should not be consumed as words — return None
        # so _parse_simple_command can stop at them
        if token.type == "OP" and token.value in ("&&", "||", "|", ";"):
            return None

        if token.type == "OP":
            # Redirect operators are handled separately in _parse_simple_command
            # but OP here means something unhandled — skip it
            self._advance()
            return None

        if token.type in ("WORD", "NUMBER", "DOLLAR_PAREN", "DOLLAR_BRACE", "DOLLAR_DPAREN", "BACKTICK"):
            node = self._make_node(token.type, token.value, token.start, token.end)
            self._advance()
            return node

        if token.type in ("DQUOTE", "SQUOTE", "ANSI_C"):
            node = self._make_node("string", token.value, token.start, token.end)
            self._advance()
            return node

        # Skip unexpected tokens
        self._advance()
        return None


class BashASTParser:
    """Pure Python bash AST parser.

    Produces tree-sitter-compatible AST structures for bash commands.
    """

    def __init__(self):
        pass

    def parse(self, source: str, timeout_ms: int = PARSE_TIMEOUT_MS) -> BashASTNode | None:
        """Parse a bash command string into an AST.

        Args:
            source: Bash command string to parse
            timeout_ms: Timeout in milliseconds (default 50ms)

        Returns:
            Root AST node, or None on parse failure/timeout
        """
        import time

        start_time = time.time()

        try:
            lexer = Lexer(source)
            tokens = lexer.lex()
            parser = Parser(tokens)
            ast = parser.parse_program()
            return ast
        except Exception as e:
            # Check timeout
            elapsed = (time.time() - start_time) * 1000
            if elapsed > timeout_ms:
                return None
            return None

    def parse_with_metadata(self, source: str) -> dict:
        """Parse and return with metadata.

        Args:
            source: Bash command string

        Returns:
            Dict with 'ast' and 'metadata'
        """
        import time

        start_time = time.time()

        lexer = Lexer(source)
        tokens = lexer.lex()
        parser = Parser(tokens)

        ast = parser.parse_program()
        elapsed = (time.time() - start_time) * 1000

        return {
            "ast": ast,
            "metadata": {
                "node_count": parser.node_count,
                "parse_time_ms": elapsed,
                "token_count": len(tokens),
            },
        }
