# mcp-server-dash

A Model Context Protocol (MCP) server that provides tools to interact with the [Dash](https://kapeli.com/dash) documentation browser API.

Dash 8 is required, which is currently in beta. You can download Dash 8 at https://blog.kapeli.com/dash-8.

<a href="https://glama.ai/mcp/servers/@Kapeli/dash-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@Kapeli/dash-mcp-server/badge" alt="Dash Server MCP server" />
</a>

## Overview

The Dash MCP server provides tools for accessing and searching documentation directly from Dash, the macOS documentation browser. MCP clients can:

- List installed docsets
- Search across docsets and code snippets
- Enable full-text search for specific docsets

### Notice

This is a work in progress. Any suggestions are welcome!

## Tools

1. **list_installed_docsets**
   - Lists all installed documentation sets in Dash
2. **search_documentation**
   - Searches across docsets and snippets
3. **enable_docset_fts**
   - Enables full-text search for a specific docset

## Requirements

- macOS (required for Dash app)
- [Dash](https://kapeli.com/dash) installed
- Python 3.11.4 or higher
- uv

## Configuration

### Using uvx

```bash
brew install uv
```

#### in `claude_desktop_config.json`

```json
{
  "mcpServers": {
      "dash-api": {
          "command": "uvx",
          "args": [
              "--from",
              "git+https://github.com/Kapeli/dash-mcp-server.git",
              "dash-mcp-server"
          ]
      }
  }
}
```

#### in `Claude Code`

```bash
claude mcp add dash-api -- uvx --from "git+https://github.com/Kapeli/dash-mcp-server.git" "dash-mcp-server"
```

### Custom API URL

By default, the server automatically detects the Dash API server running on localhost. If you need to use a custom Dash API URL (e.g., for remote Dash instances or custom configurations), you can set the `DASH_API_URL` environment variable:

#### in `claude_desktop_config.json`

```json
{
  "mcpServers": {
      "dash-api": {
          "command": "uvx",
          "args": [
              "--from",
              "git+https://github.com/Kapeli/dash-mcp-server.git",
              "dash-mcp-server"
          ],
          "env": {
              "DASH_API_URL": "http://your-custom-dash-api-url:port"
          }
      }
  }
}
```

#### in `Claude Code`

```bash
DASH_API_URL="http://your-custom-dash-api-url:port" claude mcp add dash-api -- uvx --from "git+https://github.com/Kapeli/dash-mcp-server.git" "dash-mcp-server"
```

When `DASH_API_URL` is set, the server will:
- Skip automatic port detection and Dash launching
- Use the provided URL directly
- Perform a health check to ensure the API is responding