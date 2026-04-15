# Claude API - Multi-Language Reference

Use when the user wants API reference documentation for a specific programming language.

## Overview

This skill provides language-specific API documentation for building Claude integrations.

## Supported Languages

| Language | Directory | Indicators |
|----------|-----------|------------|
| Python | `python/` | `.py`, `requirements.txt`, `pyproject.toml` |
| TypeScript | `typescript/` | `.ts`, `.tsx`, `tsconfig.json`, `package.json` |
| Java | `java/` | `.java`, `pom.xml`, `build.gradle` |
| Go | `go/` | `.go`, `go.mod` |
| Ruby | `ruby/` | `.rb`, `Gemfile` |
| C# | `csharp/` | `.cs`, `.csproj` |
| PHP | `php/` | `.php`, `composer.json` |
| curl | `curl/` | (default for no indicators) |

## How Language Detection Works

1. Scan current directory for language indicators
2. Match against known file patterns
3. Load language-specific documentation
4. Provide relevant examples and best practices

## Language-Specific Documentation

### Python

Best for:
- Data processing and analysis
- ML/AI integrations
- Scripting and automation
- Backend services

Key packages:
- `anthropic` - Official Python SDK
- `anthropic-experimental` - Experimental features

### TypeScript/JavaScript

Best for:
- Web applications
- Node.js backends
- Browser extensions
- React/Vue/Angular integrations

Key packages:
- `@anthropic-ai/sdk` - Official TypeScript SDK

### Java

Best for:
- Enterprise applications
- Android development
- Spring Boot integrations
- JVM-based systems

### Go

Best for:
- High-performance services
- CLI tools
- Cloud-native applications
- Microservices

### Ruby

Best for:
- Rails applications
- Scripting
- DevOps automation
- Web development

### C#

Best for:
- .NET applications
- Unity games
- Windows development
- Azure integrations

### PHP

Best for:
- Web applications
- WordPress plugins
- Laravel applications
- Legacy systems

### curl

Best for:
- Quick testing
- Shell scripting
- API exploration
- CI/CD pipelines

## Quick Examples by Language

### Python

```python
import anthropic
client = anthropic.Anthropic()
message = client.messages.create(
    model="claude-opus-4-6",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### TypeScript

```typescript
import Anthropic from '@anthropic-ai/sdk';
const client = new Anthropic();
const message = await client.messages.create({
    model: 'claude-opus-4-6',
    messages: [{ role: 'user', content: 'Hello' }]
});
```

### Go

```go
package main

import (
    "github.com/anthropics/anthropic-sdk-go"
)

func main() {
    client := anthropic.NewClient()
    message, _ := client.Messages.Create(anthropic.MessageCreateParams{
        Model: "claude-opus-4-6",
        Messages: []anthropic.MessageParam{{
            Role: "user",
            Content: "Hello",
        }},
    })
}
```

## Getting Started

1. **Install the SDK** for your language
2. **Set your API key** as an environment variable
3. **Start with a simple request** to verify connectivity
4. **Add error handling** for production use

## Common Patterns

### Streaming Responses

All SDKs support streaming for better UX with long responses.

### Tool Use

Define tools that the model can call:
- Function definitions with schemas
- Error handling for tool failures
- Chaining multiple tool calls

### Pagination

Handle large result sets with pagination parameters.

### Rate Limiting

Implement exponential backoff for rate limit errors.
