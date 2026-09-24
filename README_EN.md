# MemU MCP Server

An MCP (Model Context Protocol) interface for the MemU memory system, built for Claude Code CLI.

[English](README_EN.md) | [简体中文](README.md)

## Features

- **Save Memory** - persist important information to the memory system
- **Semantic Search** - query memories in natural language (semantic, not keyword matching)
- **Context Retrieval** - intelligently fetch session-relevant historical memories
- **Statistics** - inspect memory system usage

## Architecture

```
Claude Code CLI
    ↓ (MCP protocol)
MCP Server (tool layer)
    ↓ (calls)
memu_utils (helper layer)
    ↓ (storage)
MemU Service + PostgreSQL + pgvector
```

## Installation

### 1. Dependencies

```bash
pip install -r requirements.txt

# or with uv (recommended)
uv pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the MemU working directory (loaded automatically at startup):

```env
# Tongyi Qianwen LLM
DASHSCOPE_API_KEY=your_dashscope_api_key

# PostgreSQL
DATABASE_TYPE=postgres
POSTGRES_DSN=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/memu
```

### 3. MCP Configuration

Add to `.mcp.json`:

```json
{
  "mcpServers": {
    "memu": {
      "type": "stdio",
      "command": "python",
      "args": ["server.py"],
      "cwd": "/absolute/path/to/memu-mcp"
    }
  }
}
```

> Alternatively run it as a standalone HTTP service: `python server.py --transport http --host 127.0.0.1 --port 3335`, then configure `"type": "http", "url": "http://127.0.0.1:3335/mcp"`. See [docs/INSTALL.md](docs/INSTALL.md) for full deployment steps.

## MCP Tools

### 1. save_memory

Save a new memory to the MemU system.

**Parameters:**
- `content` (required): memory content
- `category` (optional): memory category
- `metadata` (optional): extra metadata
- `importance` (optional): importance score (0-1)

**Example:**
```python
save_memory(
    content="User prefers the Vim editor",
    category="preferences",
    importance=0.8
)
```

### 2. search_memory

Semantic search for relevant memories.

**Parameters:**
- `query` (required): natural-language query
- `limit` (optional): number of results (default 5, max 20)
- `category` (optional): filter by category

### 3. get_context_memories

Fetch session-relevant context memories (for session startup).

**Parameters:**
- `query` (required): description of the current task or context
- `max_tokens` (optional): token budget (default 1000)
- `limit` (optional): max number of memories (default 10)

### 4. get_memory_stats

Get memory system statistics.

**Returns:** `total_memories`, `categories`, `last_updated`

### 5. format_memories_for_context

Format a JSON memory list into Markdown context.

**Parameters:**
- `memories_json` (required): memory list in JSON format

## Usage

### Via MCP protocol (recommended)

Use the MCP tools directly in Claude Code CLI conversations.

### Via memu_utils directly (fallback)

```python
import memu_utils

result = memu_utils.save_memory(
    "User prefers the Vim editor",
    category="preferences"
)

memories = memu_utils.search_memory("editor", limit=5)

context = memu_utils.format_memories_for_context(memories)
print(context)
```

## Development

```bash
# Test MemU basics
python memu_utils.py test

# Statistics
python memu_utils.py stats

# Health check
python memu_utils.py health
```

## Tech Stack

- **Protocol**: Model Context Protocol
- **Protocol layer**: Hand-written MCP protocol (JSON-RPC 2.0, stdlib only)
- **Memory engine**: MemU (memu-py)
- **Vector store**: PostgreSQL + pgvector
- **Embedding**: Tongyi Qianwen text-embedding-v4
- **LLM**: Tongyi Qianwen qwen-plus

## Notes

1. `memu_utils.py` is kept as a direct-call fallback
2. Make sure `.env` is configured correctly
3. PostgreSQL must be running
4. The DashScope (Tongyi Qianwen) API key must be valid

## References

- [MemU GitHub](https://github.com/NevaMind-AI/Memu)
- [MCP specification](https://modelcontextprotocol.io/)

## Author

OstrichHermit

## License

MIT

## Version

1.0.0 - 2026-09-24
- Protocol layer rewritten: hand-written JSON-RPC 2.0 (stdio + streamable HTTP), FastMCP dependency removed
- 7 MCP tools, fully compatible with the 0.1.0 interface
- Generalized environment configuration (MEMU_ENV_FILE / MEMU_RESOURCES_DIR)

0.1.0 - 2026-03-04
- Initial release
- 5 MCP tools
- PostgreSQL + pgvector storage
