from typing import Optional
import httpx
import subprocess
import json
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

mcp = FastMCP("Dash Documentation API")


async def check_api_health(ctx: Context, base_url: str) -> bool:
    """Check if the Dash API server is responding at the given URL."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{base_url}/health")
            response.raise_for_status()
        await ctx.debug(f"Successfully connected to Dash API at {base_url}")
        return True
    except Exception as e:
        await ctx.debug(f"Health check failed for {base_url}: {e}")
        return False


async def working_api_base_url(ctx: Context) -> Optional[str]:
    # Check for custom API URL from environment variable first
    custom_url = os.getenv("DASH_API_URL")
    if custom_url:
        await ctx.debug(f"Using custom Dash API URL from DASH_API_URL: {custom_url}")
        if await check_api_health(ctx, custom_url):
            return custom_url
        else:
            await ctx.error(f"Custom Dash API URL is not responding: {custom_url}")
            return None
    
    # Fall back to automatic detection
    dash_running = await ensure_dash_running(ctx)
    if not dash_running:
        return None
    
    port = await get_dash_api_port(ctx)
    if port is None:
        # Try to automatically enable the Dash API Server
        await ctx.info("The Dash API Server is not enabled. Attempting to enable it automatically...")
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
            port = await get_dash_api_port(ctx)
            if port is None:
                await ctx.error("Failed to enable Dash API Server automatically. Please enable it manually in Dash Settings > Integration")
                return None
            else:
                await ctx.info("Successfully enabled Dash API Server")
        except Exception as e:
            await ctx.error("Failed to enable Dash API Server automatically. Please enable it manually in Dash Settings > Integration")
            return None
    
    return f"http://127.0.0.1:{port}"


async def get_dash_api_port(ctx: Context) -> Optional[int]:
    """Get the Dash API port from the status.json file and verify the API server is responding."""
    status_file = Path.home() / "Library" / "Application Support" / "Dash" / ".dash_api_server" / "status.json"
    
    try:
        with open(status_file, 'r') as f:
            status_data = json.load(f)
            port = status_data.get('port')
            if port is None:
                return None
                
        # Check if the API server is actually responding
        base_url = f"http://127.0.0.1:{port}"
        if await check_api_health(ctx, base_url):
            return port
        else:
            return None
            
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



class DocsetResult(BaseModel):
    """Information about a docset."""
    name: str = Field(description="Display name of the docset")
    identifier: str = Field(description="Unique identifier")
    platform: str = Field(description="Platform/type of the docset")
    full_text_search: str = Field(description="Full-text search status: 'not supported', 'disabled', 'indexing', or 'enabled'")
    notice: Optional[str] = Field(description="Optional notice about the docset status", default=None)


class DocsetResults(BaseModel):
    """Result from listing docsets."""
    docsets: list[DocsetResult] = Field(description="List of installed docsets", default_factory=list)
    error: Optional[str] = Field(description="Error message if there was an issue", default=None)


class SearchResult(BaseModel):
    """A search result from documentation."""
    name: str = Field(description="Name of the documentation entry")
    type: str = Field(description="Type of result (Function, Class, etc.)")
    platform: Optional[str] = Field(description="Platform of the result", default=None)
    load_url: str = Field(description="URL to load the documentation")
    docset: Optional[str] = Field(description="Name of the docset", default=None)
    description: Optional[str] = Field(description="Additional description", default=None)
    language: Optional[str] = Field(description="Programming language (snippet results only)", default=None)
    tags: Optional[str] = Field(description="Tags (snippet results only)", default=None)


class SearchResults(BaseModel):
    """Result from searching documentation."""
    results: list[SearchResult] = Field(description="List of search results", default_factory=list)
    error: Optional[str] = Field(description="Error message if there was an issue", default=None)


def estimate_tokens(obj) -> int:
    """Estimate token count for a serialized object. Rough approximation: 1 token ≈ 4 characters."""
    if isinstance(obj, str):
        return max(1, len(obj) // 4)
    elif isinstance(obj, (list, tuple)):
        return sum(estimate_tokens(item) for item in obj)
    elif isinstance(obj, dict):
        return sum(estimate_tokens(k) + estimate_tokens(v) for k, v in obj.items())
    elif hasattr(obj, 'model_dump'):  # Pydantic model
        return estimate_tokens(obj.model_dump())
    else:
        return max(1, len(str(obj)) // 4)


@mcp.tool()
async def list_installed_docsets(ctx: Context) -> DocsetResults:
    """List all installed documentation sets in Dash. An empty list is returned if the user has no docsets installed. 
    Results are automatically truncated if they would exceed 25,000 tokens."""
    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return DocsetResults(error="Failed to connect to Dash API Server. Please ensure Dash is running and the API server is enabled (Settings > Integration, or run open -b com.kapeli.dashdoc, followed by defaults write com.kapeli.dashdoc DHAPIServerEnabled YES).")
        await ctx.debug("Fetching installed docsets from Dash API")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/docsets/list")
            response.raise_for_status()
            result = response.json()
        
        docsets = result.get("docsets", [])
        await ctx.info(f"Found {len(docsets)} installed docsets")
        
        # Build result list with token limit checking
        token_limit = 25000
        current_tokens = 100  # Base overhead for response structure
        limited_docsets = []
        
        for docset in docsets:
            docset_info = DocsetResult(
                name=docset["name"],
                identifier=docset["identifier"],
                platform=docset["platform"],
                full_text_search=docset["full_text_search"],
                notice=docset.get("notice")
            )
            
            # Estimate tokens for this docset
            docset_tokens = estimate_tokens(docset_info)
            
            if current_tokens + docset_tokens > token_limit:
                await ctx.warning(f"Token limit reached. Returning {len(limited_docsets)} of {len(docsets)} docsets to stay under 25k token limit.")
                break
                
            limited_docsets.append(docset_info)
            current_tokens += docset_tokens
        
        if len(limited_docsets) < len(docsets):
            await ctx.info(f"Returned {len(limited_docsets)} docsets (truncated from {len(docsets)} due to token limit)")
        
        return DocsetResults(docsets=limited_docsets)
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await ctx.warning("No docsets found. Install some in Settings > Downloads.")
            return DocsetResults(error="No docsets found. Instruct the user to install some docsets in Settings > Downloads.")
        return DocsetResults(error=f"HTTP error: {e}")
    except Exception as e:
        await ctx.error(f"Failed to get installed docsets: {e}")
        return DocsetResults(error=f"Failed to get installed docsets: {e}")


@mcp.tool()
async def search_documentation(
    ctx: Context,
    query: str,
    docset_identifiers: str,
    search_snippets: bool = True,
    max_results: int = 100,
) -> SearchResults:
    """
    Search for documentation across docset identifiers and snippets.
    
    Args:
        query: The search query string
        docset_identifiers: Comma-separated list of docset identifiers to search in (from list_installed_docsets)
        search_snippets: Whether to include snippets in search results
        max_results: Maximum number of results to return (1-1000)
    
    Results are automatically truncated if they would exceed 25,000 tokens.
    """
    if not query.strip():
        await ctx.error("Query cannot be empty")
        return SearchResults(error="Query cannot be empty")
    
    if not docset_identifiers.strip():
        await ctx.error("docset_identifiers cannot be empty. Get the docset identifiers using list_installed_docsets")
        return SearchResults(error="docset_identifiers cannot be empty. Get the docset identifiers using list_installed_docsets")
    
    if max_results < 1 or max_results > 1000:
        await ctx.error("max_results must be between 1 and 1000")
        return SearchResults(error="max_results must be between 1 and 1000")
    
    try:
        base_url = await working_api_base_url(ctx)
        if base_url is None:
            return SearchResults(error="Failed to connect to Dash API Server. Please ensure Dash is running and the API server is enabled (Settings > Integration, or run open -b com.kapeli.dashdoc, followed by defaults write com.kapeli.dashdoc DHAPIServerEnabled YES).")
        
        params = {
            "query": query,
            "docset_identifiers": docset_identifiers,
            "search_snippets": search_snippets,
            "max_results": max_results,
        }
        
        await ctx.debug(f"Searching Dash API with query: '{query}'")
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(f"{base_url}/search", params=params)
            response.raise_for_status()
            result = response.json()
        
        # Check for warning message in response
        warning_message = None
        if "message" in result:
            warning_message = result["message"]
            await ctx.warning(warning_message)
        
        results = result.get("results", [])
        await ctx.info(f"Found {len(results)} results")
        
        # Build result list with token limit checking
        token_limit = 25000
        current_tokens = 100  # Base overhead for response structure
        limited_results = []
        
        for item in results:
            search_result = SearchResult(
                name=item["name"],
                type=item["type"],
                platform=item.get("platform"),
                load_url=item["load_url"],
                docset=item.get("docset"),
                description=item.get("description"),
                language=item.get("language"),
                tags=item.get("tags")
            )
            
            # Estimate tokens for this result
            result_tokens = estimate_tokens(search_result)
            
            if current_tokens + result_tokens > token_limit:
                await ctx.warning(f"Token limit reached. Returning {len(limited_results)} of {len(results)} results to stay under 25k token limit.")
                break
                
            limited_results.append(search_result)
            current_tokens += result_tokens
        
        if len(limited_results) < len(results):
            await ctx.info(f"Returned {len(limited_results)} results (truncated from {len(results)} due to token limit)")
        
        return SearchResults(results=limited_results, error=warning_message)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            error_text = e.response.text
            if "Docset with identifier" in error_text and "not found" in error_text:
                await ctx.error("Invalid docset identifier. Run list_installed_docsets to see available docsets.")
                return SearchResults(error="Invalid docset identifier. Run list_installed_docsets to see available docsets, then use the exact identifier from that list.")
            elif "No docsets found" in error_text:
                await ctx.error("No valid docsets found for search.")
                return SearchResults(error="No valid docsets found for search. Either provide valid docset identifiers from list_installed_docsets, or set search_snippets=true to search snippets only.")
            else:
                await ctx.error(f"Bad request: {error_text}")
                return SearchResults(error=f"Bad request: {error_text}. Please ensure Dash is running and the API server is enabled (Settings > Integration, or run open -b com.kapeli.dashdoc, followed by defaults write com.kapeli.dashdoc DHAPIServerEnabled YES).")
        elif e.response.status_code == 403:
            error_text = e.response.text
            if "API access blocked due to Dash trial expiration" in error_text:
                await ctx.error("Dash trial expired. Purchase Dash to continue using the API.")
                return SearchResults(error="Your Dash trial has expired. Purchase Dash at https://kapeli.com/dash to continue using the API. During trial expiration, API access is blocked.")
            else:
                await ctx.error(f"Forbidden: {error_text}")
                return SearchResults(error=f"Forbidden: {error_text}. Please ensure Dash is running and the API server is enabled (Settings > Integration, or run open -b com.kapeli.dashdoc, followed by defaults write com.kapeli.dashdoc DHAPIServerEnabled YES).")
        await ctx.error(f"HTTP error: {e}")
        return SearchResults(error=f"HTTP error: {e}. Please ensure Dash is running and the API server is enabled (Settings > Integration, or run open -b com.kapeli.dashdoc, followed by defaults write com.kapeli.dashdoc DHAPIServerEnabled YES).")
    except Exception as e:
        await ctx.error(f"Search failed: {e}")
        return SearchResults(error=f"Search failed: {e}. Please ensure Dash is running and the API server is enabled (Settings > Integration, or run open -b com.kapeli.dashdoc, followed by defaults write com.kapeli.dashdoc DHAPIServerEnabled YES).")


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
