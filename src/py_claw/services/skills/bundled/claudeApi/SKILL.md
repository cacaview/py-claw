# Claude API Reference

Use when the user wants to build applications using the Claude Code SDK or API, or when you need to understand Claude Code's programmatic interfaces.

## What This Skill Provides

1. **API Reference** - Detailed documentation for Claude Code SDKs
2. **Code Examples** - Working examples in multiple languages
3. **Best Practices** - Recommended patterns for Claude Code integrations
4. **Troubleshooting** - Common issues and solutions

## Supported Languages

- Python (`pip install anthropic`)
- TypeScript/JavaScript (`npm install @anthropic-ai/sdk`)
- curl (REST API)

## Python SDK

### Installation

```bash
pip install anthropic
```

### Basic Usage

```python
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ]
)

print(message.content)
```

### Streaming Responses

```python
with client.messages.stream(
    model="claude-opus-4-6",
    messages=[{"role": "user", "content": "Tell me a story"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

### Tool Use

```python
from anthropic import Anthropic, ToolUse

client = Anthropic()

message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "What's the weather?"}],
    tools=[
        {
            "name": "weather",
            "description": "Get weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                }
            }
        }
    ]
)

for block in message.content:
    if block.type == "tool_use":
        print(f"Tool: {block.name}")
        print(f"Input: {block.input}")
```

### Error Handling

```python
import anthropic

try:
    message = client.messages.create(
        model="claude-opus-4-6",
        messages=[{"role": "user", "content": "Hello"}]
    )
except anthropic.RateLimitError:
    print("Rate limit exceeded. Wait before retrying.")
except anthropic.AuthenticationError:
    print("Invalid API key.")
except Exception as e:
    print(f"Error: {e}")
```

## TypeScript SDK

### Installation

```bash
npm install @anthropic-ai/sdk
```

### Basic Usage

```typescript
import Anthropic from '@anthropic-ai/sdk';

const client = new Anthropic();

async function main() {
  const message = await client.messages.create({
    model: 'claude-opus-4-6',
    max_tokens: 1024,
    messages: [
      { role: 'user', content: 'Hello, Claude!' }
    ]
  });

  console.log(message.content);
}

main();
```

### Streaming

```typescript
const stream = await client.messages.stream({
  model: 'claude-opus-4-6',
  messages: [{ role: 'user', content: 'Tell me a story' }]
});

for await (const text of stream.textStream) {
  process.stdout.write(text);
}
```

## REST API (curl)

### Authentication

```bash
export ANTHROPIC_API_KEY="your-api-key"
```

### Create Message

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Streaming

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-opus-4-6",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Count to 5"}],
    "stream": true
  }'
```

## SDK Configuration Options

### Client Configuration

| Option | Python | TypeScript | Description |
|--------|--------|------------|-------------|
| api_key | `api_key` | `apiKey` | API key for authentication |
| base_url | `base_url` | `baseURL` | Custom API endpoint |
| timeout | `timeout` | `timeout` | Request timeout in seconds |
| max_retries | `max_retries` | `maxRetries` | Maximum retry attempts |

### Message Creation Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| model | string | required | Model identifier |
| messages | array | required | Conversation messages |
| max_tokens | integer | - | Maximum tokens in response |
| temperature | float | 1.0 | Response variability (0-1) |
| top_p | float | - | Nucleus sampling threshold |
| tools | array | - | Available tools |
| system | string | - | System prompt |

## Best Practices

### 1. Use Appropriate Models

- `claude-opus-4-6`: Complex reasoning, analysis
- `claude-sonnet-4-6`: Balanced performance
- `claude-haiku-4-5-20251001`: Fast responses

### 2. Handle Rate Limits

```python
import time
from anthropic import RateLimitError

for attempt in range(3):
    try:
        message = client.messages.create(...)
        break
    except RateLimitError:
        wait = 2 ** attempt
        time.sleep(wait)
```

### 3. Stream for Long Responses

Always use streaming for responses over 1000 tokens to:
- Improve perceived latency
- Avoid request timeouts
- Provide better UX

### 4. Validate Tool Inputs

Always validate tool inputs before processing:

```python
def get_weather(location: str) -> str:
    if not location or len(location) > 100:
        raise ValueError("Invalid location")
    # Proceed with weather lookup
```

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| 400 | BadRequestError | Invalid request parameters |
| 401 | AuthenticationError | Invalid or missing API key |
| 403 | PermissionError | Insufficient permissions |
| 404 | NotFoundError | Resource not found |
| 429 | RateLimitError | Rate limit exceeded |
| 500 | InternalServerError | Server-side error |

## Rate Limits

| Plan | Requests/min | Tokens/min |
|------|--------------|------------|
| Free | 5 | 10,000 |
| Pro | 60 | 100,000 |
| Team | 200 | 200,000 |
| Enterprise | Custom | Custom |

## Additional Resources

- SDK Documentation: https://docs.anthropic.com/
- API Reference: https://docs.anthropic.com/en/api/
- Python SDK: https://pypi.org/project/anthropic/
- TypeScript SDK: https://www.npmjs.com/package/@anthropic-ai/sdk
