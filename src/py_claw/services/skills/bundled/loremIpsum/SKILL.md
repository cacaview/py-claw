# Lorem Ipsum Generator

Generate placeholder/filler text for testing purposes, particularly useful for testing long context handling, token counting, and context window limits.

## Purpose

Generate realistic-sounding placeholder text that can be used to:
- Test context window limits
- Verify token counting behavior
- Fill context for testing Claude Code responses
- Simulate long documents

## When to Use

Use when:
- Testing how Claude Code handles very long contexts
- Verifying token counting and context management
- Creating test scenarios with large amounts of text
- Generating placeholder content for templates

## How It Works

The generator creates text by randomly selecting from a curated list of common English words (all verified to tokenize as single tokens). Text is structured into sentences and paragraphs.

### Token Generation

- Each word is selected randomly from a pool of ~200 common words
- Sentences are 10-20 words
- Paragraph breaks occur with ~20% probability after sentences
- The text is grammatically nonsensical but looks realistic

### Output Format

```
word word word word word word word word word word. word word word...

word word word word word word word word word word word word word. word...
```

## Usage

### Basic Usage

Generate 10,000 tokens (default):

```
/lorem-ipsum
```

### Custom Token Count

Specify the number of tokens you want:

```
/lorem-ipsum 50000
```

### Common Token Counts

| Tokens | Use Case |
|--------|----------|
| 1,000 | Quick test |
| 10,000 | Default, good for basic testing |
| 50,000 | Testing context limits |
| 100,000+ | Stress testing context window |

## Safety Limits

- Maximum generation capped at 500,000 tokens for safety
- Generation is deterministic based on Python's random module
- Text is pseudo-random, not truly lorem ipsum

## Notes

- This is primarily useful for testing and development
- The generated text is not grammatical but looks realistic
- Each invocation generates different text (random selection)
- Token counts are approximate (based on word count)
