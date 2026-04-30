"""AAP Scanner Agent - Discovers live state from AAP instance via MCP servers."""

from crewai import Agent

from src.config import get_maas_llm
from src.tools.mcp_tools import (
    get_aap_current_state_mcp,
    get_aap_object_mcp,
    list_aap_objects_mcp,
)


def create_aap_scanner_agent() -> Agent:
    """Create the AAP Scanner Agent.

    This agent is responsible for:
    - Querying each AAP MCP domain server (job_management, platform_configuration,
      inventory_management, security_compliance, user_management)
    - Fetching all objects of each managed type
    - Building a complete picture of the current AAP state for drift analysis
    """
    return Agent(
        role="AAP State Scanner",
        goal=(
            "Connect to the Ansible Automation Platform via MCP servers and discover "
            "the current state of all managed objects. Build a complete inventory of "
            "projects, job templates, inventories, credentials, and other objects "
            "as they exist in AAP right now."
        ),
        backstory=(
            "You are an expert at querying Ansible Automation Platform state through "
            "the MCP protocol. You use dedicated AAP MCP domain servers — "
            "job_management for projects and job templates, platform_configuration "
            "for organizations/credential types/execution environments, "
            "inventory_management for inventories, security_compliance for credentials, "
            "and user_management for teams. You efficiently discover all objects, "
            "normalise responses, and capture the exact current state of AAP for "
            "comparison against the desired state in Git."
        ),
        tools=[
            list_aap_objects_mcp,
            get_aap_object_mcp,
            get_aap_current_state_mcp,
        ],
        llm=get_maas_llm(),
        verbose=True,
        allow_delegation=False,
    )
