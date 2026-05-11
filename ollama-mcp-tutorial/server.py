"""
=============================================================================
AEM CONTENT ASSISTANT — MCP server for Adobe Experience Manager
=============================================================================

This server turns an AI model into an AEM content assistant.
It provides tools to fetch data from AEM JSON endpoints
and analyze page structure.

How it works:
  AEM can expose page data as JSON via several suffixes:
    /content/mysite/page.model.json        — Sling Model Exporter (components)
    /content/mysite/page.infinity.json     — full JCR node tree
    /content/mysite/page._jcr_content.json — jcr:content node only
    /your/custom/servlet.json              — any custom servlet

  The MCP server fetches this JSON and lets the AI analyze it.

Tools:
  - fetch_aem_json          : fetch raw JSON from any AEM URL
  - get_page_content        : extract all readable text from a page
  - analyze_page_components : show the component structure of a page
  - compare_pages           : compare two pages (components and content)
=============================================================================
"""

import sys
import json
import httpx                           # Async HTTP client
from typing import Any

from mcp.server.fastmcp import FastMCP

# Force UTF-8 output (required on Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# =============================================================================
# SERVER CONFIGURATION
# =============================================================================

mcp = FastMCP(name="AEMContentAssistant")

# Base URL of your AEM instance.
# Can be overridden directly in the URL when calling tools.
AEM_BASE_URL = "http://localhost:4502"

# Basic Auth for AEM (default credentials for local development).
# For production, pass credentials via environment variables.
AEM_AUTH = ("admin", "admin")

# HTTP request timeout in seconds
HTTP_TIMEOUT = 15.0


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_text_values(data: Any, max_length: int = 5000) -> list[str]:
    """
    Recursively walks the JSON structure and collects all string values
    that look like readable content (not AEM technical metadata fields).

    Skips keys starting with ":" (JCR metadata like :type, :name)
    and keys with typical AEM technical names.
    """
    SKIP_KEYS = {
        "jcr:primaryType", "jcr:mixinTypes", "jcr:uuid", "jcr:created",
        "jcr:createdBy", "jcr:lastModified", "jcr:lastModifiedBy",
        "cq:lastModified", "cq:lastModifiedBy", "cq:lastReplicated",
        "sling:resourceType", "sling:resourceSuperType",
        ":type", ":name", ":path", "id", "dataLayerBuilt",
    }
    results = []
    total_len = 0

    def _walk(node: Any):
        nonlocal total_len
        if total_len >= max_length:
            return
        if isinstance(node, str):
            # Keep strings longer than 3 chars that don't look like paths/types
            if len(node) > 3 and not node.startswith("/") and "/" not in node[:20]:
                results.append(node)
                total_len += len(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key not in SKIP_KEYS and not key.startswith(":"):
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return results


def _collect_components(data: Any, path: str = "", depth: int = 0) -> list[dict]:
    """
    Recursively collects component information from the AEM JSON structure.
    Returns a list of dicts with path, type, and a text preview of each component.
    """
    components = []
    if not isinstance(data, dict):
        return components

    resource_type = data.get("sling:resourceType", data.get(":type", ""))
    if resource_type:
        # Extract the short component name from the resource type path
        component_name = resource_type.split("/")[-1] if "/" in resource_type else resource_type

        # Collect text fields from this component
        text_fields = []
        for key in ("text", "title", "description", "heading", "jcr:title",
                    "linkText", "actionText", "label", "alt", "caption"):
            if key in data and isinstance(data[key], str) and data[key].strip():
                text_fields.append(f'{key}: "{data[key][:80]}"')

        components.append({
            "path": path or "/",
            "type": component_name,
            "resource_type": resource_type,
            "depth": depth,
            "content_preview": "; ".join(text_fields[:3]) if text_fields else "(no text)",
        })

    # Recursively walk child nodes
    for key, value in data.items():
        if isinstance(value, dict) and not key.startswith(":"):
            child_path = f"{path}/{key}" if path else f"/{key}"
            components.extend(_collect_components(value, child_path, depth + 1))

    return components


async def _fetch_json(url: str) -> tuple[dict | None, str | None]:
    """
    Performs a GET request to an AEM URL and returns (data, error).
    Supports Basic Auth.

    Returns (json_data, None) on success
    or (None, error_message) on failure.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url,
                auth=AEM_AUTH,
                timeout=HTTP_TIMEOUT,
                headers={"Accept": "application/json"},
                follow_redirects=True,
            )
        except httpx.ConnectError:
            return None, (
                f"Could not connect to {url}. "
                "Make sure AEM is running and the URL is correct."
            )
        except httpx.TimeoutException:
            return None, f"Request to {url} timed out (>{HTTP_TIMEOUT}s)."

        if response.status_code == 401:
            return None, (
                "Authentication error (401). "
                "Check AEM_AUTH in server.py or your access permissions."
            )
        if response.status_code == 404:
            return None, (
                f"Page or endpoint not found (404): {url}. "
                "Check the path and suffix (.model.json, .infinity.json, etc.)."
            )
        if not response.is_success:
            return None, f"HTTP {response.status_code} for request to {url}."

        try:
            return response.json(), None
        except Exception:
            return None, f"Response is not valid JSON. Content: {response.text[:200]}"


# =============================================================================
# MCP TOOLS
# =============================================================================

@mcp.tool()
async def fetch_aem_json(url: str) -> str:
    """
    Fetches and returns JSON data from any AEM endpoint.

    This is the general-purpose tool for getting raw data from AEM.
    Use it when you need to inspect the full data structure
    or when other tools are not suitable.

    Common AEM suffixes:
      - .model.json        — Sling Model data (recommended for components)
      - .infinity.json     — full JCR node tree (large response)
      - ._jcr_content.json — jcr:content node only
      - .1.json            — first level of JCR tree
      - .json              — custom servlet or base resource

    Args:
        url: Full AEM endpoint URL including the suffix.
             Examples:
               "http://localhost:4502/content/mysite/en.model.json"
               "http://localhost:4502/api/pages/info.json"
               "http://myaem.company.com/content/site/page.model.json"

    Returns:
        Formatted JSON as a string, or an error message.
    """
    data, error = await _fetch_json(url)
    if error:
        return f"Error: {error}"

    # Limit response size to avoid overwhelming the model context
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    if len(json_str) > 8000:
        json_str = json_str[:8000] + "\n\n... [response truncated — use analyze_page_components for structural analysis]"

    return json_str


@mcp.tool()
async def get_page_content(url: str) -> str:
    """
    Extracts all readable text content from an AEM page.

    Fetches the page JSON and recursively collects all text fields
    (titles, descriptions, component texts, alt texts, etc.),
    filtering out technical JCR metadata.

    Use this tool when you need to:
      - Understand what a page is about
      - Check for specific words or phrases
      - Get content for translation or sentiment analysis
      - Compare the text content of multiple pages

    Args:
        url: AEM page URL with .model.json or .infinity.json suffix.
             Example: "http://localhost:4502/content/mysite/en/about.model.json"

    Returns:
        All text content of the page, one fragment per line.
    """
    data, error = await _fetch_json(url)
    if error:
        return f"Error: {error}"

    texts = _extract_text_values(data)
    if not texts:
        return "No text content found on the page. Try the .infinity.json suffix for the full tree."

    result = f"Page text content ({url}):\n"
    result += "─" * 60 + "\n"
    for i, text in enumerate(texts, 1):
        result += f"{i:3}. {text}\n"
    result += "─" * 60 + "\n"
    result += f"Total text fragments: {len(texts)}"
    return result


@mcp.tool()
async def analyze_page_components(url: str) -> str:
    """
    Analyzes the component structure of an AEM page.

    Fetches the page JSON and builds a component tree showing
    each component's type, depth in the structure, and a text preview.

    Use this tool when you need to:
      - Understand which components make up a page
      - Find all usages of a specific component
      - Check page structure before refactoring
      - Compare templates across different pages
      - Find pages that contain a specific component type

    Args:
        url: AEM page URL with .model.json or .infinity.json suffix.
             Example: "http://localhost:4502/content/mysite/en.model.json"

    Returns:
        A structured list of components with their types and content previews.
    """
    data, error = await _fetch_json(url)
    if error:
        return f"Error: {error}"

    components = _collect_components(data)
    if not components:
        return (
            "No components found. Make sure:\n"
            "  1. The URL includes the .model.json or .infinity.json suffix\n"
            "  2. The page has child nodes with sling:resourceType"
        )

    # Group by component type for a summary
    type_counts: dict[str, int] = {}
    for comp in components:
        t = comp["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    result = f"Page component structure ({url}):\n"
    result += "═" * 60 + "\n"

    for comp in components:
        indent = "  " * comp["depth"]
        result += f"{indent}▸ [{comp['type']}]\n"
        result += f"{indent}  Path: {comp['path']}\n"
        if comp["content_preview"] != "(no text)":
            result += f"{indent}  Content: {comp['content_preview']}\n"
        result += "\n"

    result += "═" * 60 + "\n"
    result += "Component type summary:\n"
    for comp_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        result += f"  {comp_type}: {count}\n"
    result += f"\nTotal components: {len(components)}"

    return result


@mcp.tool()
async def compare_pages(url1: str, url2: str) -> str:
    """
    Compares two AEM pages by component structure and text content.

    Fetches both pages in parallel and produces a diff report:
    which components exist on one page but not the other,
    and how component types are used similarly or differently.

    Use this tool when you need to:
      - Compare a reference page with its copy
      - Find differences between language versions of a page
      - Verify that a page conforms to a template
      - Understand why two pages look different

    Args:
        url1: URL of the first page (with .model.json or .infinity.json suffix).
              Example: "http://localhost:4502/content/site/en/page1.model.json"
        url2: URL of the second page to compare.
              Example: "http://localhost:4502/content/site/en/page2.model.json"

    Returns:
        A report of similarities and differences between the two pages.
    """
    import asyncio

    # Fetch both pages in parallel (not sequentially) for speed
    (data1, err1), (data2, err2) = await asyncio.gather(
        _fetch_json(url1),
        _fetch_json(url2),
    )

    if err1:
        return f"Error loading page 1: {err1}"
    if err2:
        return f"Error loading page 2: {err2}"

    # Collect component type sets for each page
    components1 = _collect_components(data1)
    components2 = _collect_components(data2)

    types1 = {c["type"] for c in components1}
    types2 = {c["type"] for c in components2}

    only_in_1 = types1 - types2
    only_in_2 = types2 - types1
    common = types1 & types2

    # Collect texts for content volume comparison
    texts1 = _extract_text_values(data1)
    texts2 = _extract_text_values(data2)

    result = "PAGE COMPARISON\n"
    result += "═" * 60 + "\n\n"

    result += f"Page 1: {url1}\n"
    result += f"  Components: {len(components1)}, text fragments: {len(texts1)}\n\n"

    result += f"Page 2: {url2}\n"
    result += f"  Components: {len(components2)}, text fragments: {len(texts2)}\n\n"

    result += "─" * 60 + "\n"
    result += f"Shared components ({len(common)}):\n"
    for t in sorted(common):
        result += f"  ✓ {t}\n"

    if only_in_1:
        result += f"\nOnly on page 1 ({len(only_in_1)}):\n"
        for t in sorted(only_in_1):
            result += f"  ← {t}\n"

    if only_in_2:
        result += f"\nOnly on page 2 ({len(only_in_2)}):\n"
        for t in sorted(only_in_2):
            result += f"  → {t}\n"

    if not only_in_1 and not only_in_2:
        result += "\n✅ Both pages use the same set of components.\n"

    result += "\n─" * 60 + "\n"
    diff_count = abs(len(texts1) - len(texts2))
    result += f"Content volume difference: ~{diff_count} text fragments"

    return result


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    mcp.run(transport="stdio")
