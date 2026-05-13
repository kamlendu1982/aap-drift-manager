"""MCP-based tools for querying AAP state via AAP MCP domain servers.

These tools replace the direct REST API tools used by the aap_scanner agent.
They query AAP through the MCP protocol, connecting to the appropriate domain
server based on the object type being requested:

  - job_management         → projects, job_templates, workflow_job_templates
  - platform_configuration → organizations, credential_types, execution_environments
  - inventory_management   → inventories
  - security_compliance    → credentials
  - user_management        → teams
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from crewai.tools import tool

from src.config import get_settings

# Mapping: object_type → mcp_domain
# The actual tool name ({object_type}_list) is discovered dynamically at runtime.
OBJECT_TYPE_DOMAIN_MAP: Dict[str, str] = {
    "organizations":          "platform_configuration",
    "teams":                  "user_management",
    "credential_types":       "platform_configuration",
    "execution_environments": "platform_configuration",
    "projects":               "job_management",
    "inventories":            "inventory_management",
    "credentials":            "security_compliance",
    "job_templates":          "job_management",
    "workflow_job_templates": "job_management",
}

# Cache: domain → list of available tool names (populated on first use)
_tool_name_cache: Dict[str, List[str]] = {}


# ── URL / Auth helpers ─────────────────────────────────────────────────────────

def _get_mcp_url(domain: str) -> str:
    """Build the MCP server URL for a given domain."""
    settings = get_settings()
    parsed = urlparse(settings.aap_url)
    host = parsed.hostname
    scheme = parsed.scheme
    port = settings.aap_mcp_port
    return f"{scheme}://{host}:{port}/{domain}/mcp"


def _get_auth_headers() -> Dict[str, str]:
    """Return Bearer auth header if an AAP token is configured."""
    settings = get_settings()
    if settings.aap_token:
        return {"Authorization": f"Bearer {settings.aap_token}"}
    return {}


def _make_httpx_client(headers: dict, timeout: httpx.Timeout, **kwargs) -> httpx.AsyncClient:
    """httpx_client_factory that disables TLS verification when AAP_VERIFY_SSL=false."""
    return httpx.AsyncClient(headers=headers, timeout=timeout, verify=False, **kwargs)


# ── Async MCP helpers ──────────────────────────────────────────────────────────

async def _list_mcp_tools_async(domain: str) -> List[str]:
    """Return all tool names available on the given MCP domain server."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    settings = get_settings()
    url = _get_mcp_url(domain)
    headers = _get_auth_headers()
    factory = _make_httpx_client if not settings.aap_verify_ssl else None

    async with streamablehttp_client(
        url=url,
        headers=headers,
        httpx_client_factory=factory,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools_response = await session.list_tools()
            return [t.name for t in tools_response.tools]


async def _call_mcp_tool_async(
    domain: str,
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
) -> Any:
    """Call a single tool on the given MCP domain server and return the parsed result."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    settings = get_settings()
    url = _get_mcp_url(domain)
    headers = _get_auth_headers()
    factory = _make_httpx_client if not settings.aap_verify_ssl else None

    async with streamablehttp_client(
        url=url,
        headers=headers,
        httpx_client_factory=factory,
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=args or {})

            if result.content:
                for item in result.content:
                    if hasattr(item, "text") and item.text:
                        try:
                            return json.loads(item.text)
                        except (json.JSONDecodeError, ValueError):
                            return item.text
            return {}


# ── Sync wrapper ───────────────────────────────────────────────────────────────

def _run_async(coro) -> Any:
    """Execute an async coroutine synchronously (safe inside or outside an event loop)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside a running loop (e.g. Jupyter) — run in a thread pool.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

    return asyncio.run(coro)


# ── Object-type resolution ─────────────────────────────────────────────────────

def _resolve_list_tool(object_type: str) -> Tuple[str, str]:
    """Return (domain, tool_name) for listing the given object type.

    Checks the domain's tool catalogue on first use and caches the result.
    Raises ValueError if no suitable tool is found.
    """
    domain = OBJECT_TYPE_DOMAIN_MAP.get(object_type)
    if not domain:
        raise ValueError(
            f"Object type '{object_type}' has no MCP domain mapping. "
            f"Supported types: {', '.join(sorted(OBJECT_TYPE_DOMAIN_MAP))}"
        )

    if domain not in _tool_name_cache:
        try:
            _tool_name_cache[domain] = _run_async(_list_mcp_tools_async(domain))
        except Exception as exc:
            raise RuntimeError(
                f"Could not fetch tool list from MCP server '{domain}': {exc}"
            ) from exc

    available = _tool_name_cache[domain]

    # Prefer an exact {object_type}_list match
    candidate = f"{object_type}_list"
    if candidate in available:
        return (domain, candidate)

    # Fallback: any tool whose name contains the type and "list"
    for t in available:
        if object_type in t and "list" in t:
            return (domain, t)

    raise ValueError(
        f"No list tool found for '{object_type}' on MCP server '{domain}'. "
        f"Available tools: {available}"
    )


def _list_objects_via_mcp(object_type: str) -> List[Dict[str, Any]]:
    """List all objects of the given type by calling the appropriate MCP server."""
    domain, tool_name = _resolve_list_tool(object_type)
    result = _run_async(_call_mcp_tool_async(domain, tool_name))

    if isinstance(result, dict):
        objects = result.get("results", [])
    elif isinstance(result, list):
        objects = result
    else:
        objects = []

    # Match the REST API behaviour: skip built-in (managed) credential types
    if object_type == "credential_types":
        objects = [o for o in objects if not o.get("managed", False)]

    return objects


def get_aap_state_via_mcp(object_types: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Return {object_type: {name: object_dict}} for each requested type via MCP.

    This is the MCP equivalent of AAPClient.get_current_state() and is called
    directly by diff_tools when the scanner passes its context.
    """
    return {t: {o["name"]: o for o in _list_objects_via_mcp(t)} for t in object_types}


# ── CrewAI Tool Functions ──────────────────────────────────────────────────────

@tool("List AAP objects via MCP")
def list_aap_objects_mcp(object_type: str) -> str:
    """List all objects of a specific type from AAP using the MCP server.

    Routes to the correct AAP MCP domain server based on object type:
      - job_management:         projects, job_templates, workflow_job_templates
      - platform_configuration: organizations, credential_types, execution_environments
      - inventory_management:   inventories
      - security_compliance:    credentials
      - user_management:        teams

    For credential_types, built-in (managed) types are automatically excluded.

    Args:
        object_type: e.g. 'projects', 'job_templates', 'organizations', 'credentials'
    """
    if object_type not in OBJECT_TYPE_DOMAIN_MAP:
        return (
            f"Unknown object type '{object_type}'. "
            f"Supported: {', '.join(sorted(OBJECT_TYPE_DOMAIN_MAP))}"
        )
    try:
        objects = _list_objects_via_mcp(object_type)
        if not objects:
            return f"No {object_type} found in AAP (via MCP)"
        lines = [f"Found {len(objects)} {object_type} in AAP (via MCP):"]
        for obj in objects:
            name = obj.get("name", "Unknown")
            oid = obj.get("id", "?")
            lines.append(f"  - {name} (ID: {oid})")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing {object_type} via MCP: {exc}"


@tool("Get AAP object details via MCP")
def get_aap_object_mcp(object_type: str, name: str) -> str:
    """Get detailed information about a specific AAP object using the MCP server.

    Args:
        object_type: The type of AAP object (e.g. 'job_templates', 'projects')
        name: The name of the object to retrieve
    """
    import yaml as _yaml

    if object_type not in OBJECT_TYPE_DOMAIN_MAP:
        return f"Unknown object type '{object_type}'"
    try:
        objects = _list_objects_via_mcp(object_type)
        obj = next((o for o in objects if o.get("name") == name), None)
        if not obj:
            return f"Object not found: {object_type}/{name}"
        return _yaml.dump(obj, default_flow_style=False)
    except Exception as exc:
        return f"Error getting {object_type}/{name} via MCP: {exc}"


@tool("Get AAP current state via MCP")
def get_aap_current_state_mcp(object_types: str) -> str:
    """Get the current state of AAP for comma-separated object types using MCP servers.

    Queries each AAP MCP domain server as appropriate for the requested types and
    returns a summary of objects found per type.

    Args:
        object_types: Comma-separated list, e.g. 'organizations,projects,job_templates'
    """
    types_list = [t.strip() for t in object_types.split(",") if t.strip()]
    lines = ["Current AAP State (via MCP):"]
    errors: List[str] = []

    for obj_type in types_list:
        if obj_type not in OBJECT_TYPE_DOMAIN_MAP:
            errors.append(f"  Skipped unknown type: {obj_type}")
            continue
        try:
            objects = _list_objects_via_mcp(obj_type)
            lines.append(f"\n{obj_type}: {len(objects)} objects")
            for obj in objects:
                name = obj.get("name", "Unknown")
                lines.append(f"  - {name}")
        except Exception as exc:
            errors.append(f"  Error fetching {obj_type}: {exc}")

    if errors:
        lines.append("\nErrors:")
        lines.extend(errors)

    return "\n".join(lines)
