from typing import Optional
import httpx
import subprocess
import json
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

mcp = FastMCP("Dash Documentation API")


async def working_api_base_url(ctx: Context) -> Optional[str]:
    dash_running = await ensure_dash_running(ctx)
    if not dash_running:
        return None
    
    port = get_dash_api_port()
    if port is None:
        # Use FastMCP elicit to ask user if they want to enable Dash API Server
        response = await ctx.elicit(
            "The Dash API Server is not enabled. It must be enabled in Dash Settings > Integration for this MCP server to work. "
            "Would you like me to try to enable it for you automatically?",
            ["Yes, enable it automatically", "No, I'll do it manually"]
        )
        
        if response == "Yes, enable it automatically":
            try:
                subprocess.run(
                    ["defaults", "write", "com.kapeli.dashdoc", "DHAPIServerEnabled", "YES"],
                    check=True,
                    timeout=10
                )
                # Wait a moment for Dash to pick up the change
                import time
                time.sleep(2)
                
                # Try to get the port again
                port = get_dash_api_port()
                if port is None:
                    await ctx.error("Failed to enable Dash API Server. Please make sure Dash is running and that the Dash API Server is enabled in Settings > Integration")
                    return None
            except Exception as e:
                return None
        else:
            await ctx.error("Failed to connect to Dash API Server. Please make sure Dash is running and that the Dash API Server is enabled in Settings > Integration")
            return None        
    
    # Test the connection by checking the health endpoint
    base_url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{base_url}/health")
            response.raise_for_status()
        await ctx.debug(f"Successfully connected to Dash API at {base_url}")
        return base_url
    except Exception as e:
        await ctx.error("Failed to connect to Dash API Server. Please make sure Dash is running and that the Dash API Server is enabled in Settings > Integration")
        return None


def get_dash_api_port() -> Optional[int]:
    """Get the Dash API port from the status.json file."""
    status_file = Path.home() / "Library" / "Application Support" / "Dash" / ".dash_api_server" / "status.json"
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
            return status_data.get('port')
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def check_dash_running() -> bool:
    """Check if Dash app is running by looking for the process."""
    try:
        # Use pgrep to check for Dash process
        result = subprocess.run(
            ["pgrep", "-f", "Dash"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


async def ensure_dash_running(ctx: Context) -> bool:
    """Ensure Dash is running, launching it if necessary."""
    if not check_dash_running():
        await ctx.info("Dash is not running. Launching Dash...")
        try:
            # Launch Dash using the bundle identifier
            subprocess.run(
                ["open", "-g", "-j", "-b", "com.kapeli.dashdoc"],
                check=True,
                timeout=10
            )
            # Wait a moment for Dash to start
            import time
            time.sleep(4)
            
            # Check again if Dash is now running
            if not check_dash_running():
                await ctx.error("Failed to launch Dash application")
                return False
            else:
                await ctx.info("Dash launched successfully")
                return True
        except subprocess.CalledProcessError:
            await ctx.error("Failed to launch Dash application")
            return False
        except Exception as e:
            await ctx.error(f"Error launching Dash: {e}")
            return False
    else:
        return True



class DocsetInfo(BaseModel):
    """Information about a docset."""
    name: str = Field(description="Display name of the docset")
    identifier: str = Field(description="Unique identifier")
    platform: str = Field(description="Platform/type of the docset")
    full_text_search: str = Field(description="Full-text search status: 'not supported', 'disabled', 'indexing', or 'enabled'")
    notice: Optional[str] = Field(description="Optional notice about the docset status", default=None)


class SearchResult(BaseModel):
    """A search result from documentation."""
    name: str = Field(description="Name of the documentation entry")
    type: str = Field(description="Type of result (Function, Class, etc.)")
    platform: str = Field(description="Platform of the result")
    load_url: str = Field(description="URL to load the documentation")
    docset: Optional[str] = Field(description="Name of the docset", default=None)
    description: Optional[str] = Field(description="Additional description", default=None)
    language: Optional[str] = Field(description="Programming language (snippet results only)", default=None)
    tags: Optional[str] = Field(description="Tags (snippet results only)", default=None)


@mcp.tool()
async def list_installed_docsets(ctx: Context) -> list[DocsetInfo]:
    """List all installed documentation sets in Dash. An empty list is returned if the user has no docsets installed"""
    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return []
        await ctx.debug("Fetching installed docsets from Dash API")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/docsets/list")
            response.raise_for_status()
            result = response.json()
        
        docsets = result.get("docsets", [])
        await ctx.info(f"Found {len(docsets)} installed docsets")
        
        return [
            DocsetInfo(
                name=docset["name"],
                identifier=docset["identifier"],
                platform=docset["platform"],
                full_text_search=docset["full_text_search"],
                notice=docset.get("notice")
            )
            for docset in docsets
        ]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await ctx.warning("No docsets found. Install some in Settings > Downloads.")
            return []
        await ctx.error(f"HTTP error: {e}")
        return []
    except Exception as e:
        await ctx.error(f"Failed to get installed docsets: {e}")
        return []


@mcp.tool()
async def search_documentation(
    ctx: Context,
    query: str,
    docset_identifiers: Optional[str] = None,
    search_snippets: bool = True,
    max_results: int = 100,
) -> list[SearchResult]:
    """
    Search for documentation across docset identifiers and snippets.
    
    Args:
        query: The search query string
        docset_identifiers: Comma-separated list of docset identifiers to search in (from list_installed_docsets)
        search_snippets: Whether to include snippets in search results
        max_results: Maximum number of results to return (1-1000)
    """
    if not query.strip():
        await ctx.error("Query cannot be empty")
        raise ValueError("Query cannot be empty")
    
    if max_results < 1 or max_results > 1000:
        await ctx.error("max_results must be between 1 and 1000")
        raise ValueError("max_results must be between 1 and 1000")
    
    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return []
        
        params = {
            "query": query,
            "search_snippets": search_snippets,
            "max_results": max_results,
        }
        if docset_identifiers:
            params["docset_identifiers"] = docset_identifiers
        
        await ctx.debug(f"Searching Dash API with query: '{query}'")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/search", params=params)
            response.raise_for_status()
            result = response.json()
        
        # Check for warning message in response
        if "message" in result:
            await ctx.warning(result["message"])
        
        results = result.get("results", [])
        await ctx.info(f"Found {len(results)} results")
        
        return [
            SearchResult(
                name=item["name"],
                type=item["type"],
                platform=item["platform"],
                load_url=item["load_url"],
                docset=item.get("docset"),
                description=item.get("description"),
                language=item.get("language"),
                tags=item.get("tags")
            )
            for item in results
        ]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            await ctx.error(f"Bad request: {e.response.text}")
            return []
        elif e.response.status_code == 403:
            await ctx.error(f"Forbidden: {e.response.text}")
            return []
        await ctx.error(f"HTTP error: {e}")
        return []
    except Exception as e:
        await ctx.error(f"Search failed: {e}")
        return []


@mcp.tool()
async def enable_docset_fts(ctx: Context, identifier: str) -> bool:
    """
    Enable full-text search for a specific docset.
    
    Args:
        identifier: The docset identifier (from list_installed_docsets)
        
    Returns:
        True if FTS was successfully enabled, False otherwise
    """
    if not identifier.strip():
        await ctx.error("Docset identifier cannot be empty")
        return False

    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return False
        
        await ctx.debug(f"Enabling FTS for docset: {identifier}")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/docsets/enable_fts", params={"identifier": identifier})
            response.raise_for_status()
            result = response.json()
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            await ctx.error(f"Bad request: {e.response.text}")
            return False
        elif e.response.status_code == 404:
            await ctx.error(f"Docset not found: {identifier}")
            return False
        await ctx.error(f"HTTP error: {e}")
        return False
    except Exception as e:
        await ctx.error(f"Failed to enable FTS: {e}")
        return False
    return True

def main():
    mcp.run()


if __name__ == "__main__":
    main()
