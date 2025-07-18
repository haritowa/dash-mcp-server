# mcp-server-dash

A Model Context Protocol (MCP) server that provides tools to interact with the [Dash](https://kapeli.com/dash) documentation browser API.

## Overview

The Dash MCP server provides tools for accessing and searching documentation directly from Dash, the macOS documentation browser. AI agents can:

- List installed docsets
- Search across docsets and code snippets
- Enable full-text search for specific docsets

### Tips

For best results, ensure you have relevant docsets installed in Dash for the APIs you're working with.

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

### Using uvx (recommended)

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


## License

MIT