# Remote OpenCode MCP Server

[![PyPI version](https://badge.fury.io/py/opencode-mcp.svg)](https://badge.fury.io/py/opencode-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Model Context Protocol (MCP) server that enables remote access to [OpenCode](https://opencode.ai) AI coding agent. This allows MCP-compatible clients (Claude Desktop, Cursor, etc.) to leverage OpenCode's capabilities.

## Features

- **Remote OpenCode Integration**: Connect to OpenCode instances running anywhere
- **MCP Protocol**: Full MCP server implementation with SSE transport
- **4 Core Tools**:
  - Create new sessions
  - Send prompts with automatic timeout handling
  - Check session status and history
  - List all sessions
- **Configurable Timeout**: Adjustable task timeout via environment variable
- **Authentication Support**: Optional password protection

## Requirements

- Python 3.12+
- [OpenCode](https://opencode.ai) running in **serve mode**

### OpenCode Serve Mode

This MCP server requires OpenCode to be running in serve mode with API enabled:

```bash
opencode --serve
```

Or with custom port and password:

```bash
opencode --serve --port 4096 --password your_password
```

Make sure `OPENCODE_URL` and `OPENCODE_SERVER_PASSWORD` in your `.env` match the serve command.

## Installation

### From Source

```bash
git clone https://github.com/Dirichelet/remote-opencode-mcp.git
cd remote-opencode-mcp
uv sync
```

### Using uv

```bash
uv add remote-opencode-mcp
```

## Configuration

Create a `.env` file (copy from `example.env`):

```bash
cp example.env .env
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENCODE_URL` | OpenCode server URL | `http://127.0.0.1:4096` |
| `OPENCODE_SERVER_PASSWORD` | Authentication password | (none) |
| `MCP_PORT` | MCP server port | `14962` |
| `OPENCODE_TASK_TIMEOUT` | Task wait timeout in seconds (0 for async) | `60` |

## Usage

### Start the Server

```bash
python server.py
```

Or with uv:

```bash
uv run python server.py
```

Output:

```
=========================================
🚀 OpenCode MCP Server started
🎯 Target: http://127.0.0.1:4096
⏱️ Task timeout: 60 seconds
🔗 SSE URL:  http://127.0.0.1:14962/sse
=========================================
```

### Available Tools

#### 1. `opencode_create_session`
Create a new OpenCode session.

**Input:**
```json
{
  "title": "My Task"  // optional
}
```

#### 2. `opencode_send_prompt`
Send a prompt to an existing session and wait for result.

**Input:**
```json
{
  "session_id": "ses_xxxx",
  "prompt": "Help me write a Python function"
}
```

#### 3. `opencode_check_session`
Get session status and full conversation history.

**Input:**
```json
{
  "session_id": "ses_xxxx"
}
```

#### 4. `opencode_list_sessions`
List all sessions.

**Input:**
```json
{
  "limit": 10  // optional, default 10
}
```

## MCP Client Integration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "opencode": {
      "command": "uv",
      "args": ["--directory", "/path/to/remote-opencode-mcp", "run", "python", "server.py"]
    }
  }
}
```

### Other MCP Clients

Connect to the SSE endpoint:

```
http://localhost:14962/sse
```

## Workflow Example

```
User → MCP Client → remote-opencode-mcp → OpenCode Server
                              ↓
                      1. Create session
                      2. Send prompt
                      3. Wait for result
                      4. Return to client
```

## Development

### Install Dev Dependencies

```bash
uv sync --extra dev
```

### Linting

```bash
uv run ruff check .
```

### Type Checking

```bash
uv run mypy .
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Related

- [OpenCode](https://opencode.ai) - The AI coding agent
- [MCP](https://modelcontextprotocol.io) - Model Context Protocol
