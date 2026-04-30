"""Tools package for AAP Drift Manager."""

from .git_tools import (
    GitTools,
    get_all_definitions,
    get_desired_state,
    get_full_desired_state,
    parse_yaml_file,
    pull_git_latest,
    read_git_directory,
)
from .aap_tools import (
    AAPClient,
    create_aap_object,
    delete_aap_object,
    get_aap_current_state,
    get_aap_object,
    list_aap_objects,
    update_aap_object,
)
from .mcp_tools import (
    OBJECT_TYPE_DOMAIN_MAP,
    get_aap_current_state_mcp,
    get_aap_object_mcp,
    get_aap_state_via_mcp,
    list_aap_objects_mcp,
)
from .diff_tools import (
    DiffTools,
    compare_objects,
    find_all_drift,
    generate_drift_report,
)
from .reconcile_tool import reconcile_aap_with_git

__all__ = [
    # Git Tools
    "GitTools",
    "get_all_definitions",
    "get_desired_state",
    "get_full_desired_state",
    "parse_yaml_file",
    "pull_git_latest",
    "read_git_directory",
    # AAP REST Tools (used by reconciler for write operations)
    "AAPClient",
    "create_aap_object",
    "delete_aap_object",
    "get_aap_current_state",
    "get_aap_object",
    "list_aap_objects",
    "update_aap_object",
    # AAP MCP Tools (used by scanner agent for read operations)
    "OBJECT_TYPE_DOMAIN_MAP",
    "get_aap_current_state_mcp",
    "get_aap_object_mcp",
    "get_aap_state_via_mcp",
    "list_aap_objects_mcp",
    # Diff Tools
    "DiffTools",
    "compare_objects",
    "find_all_drift",
    "generate_drift_report",
    # Reconcile Tool
    "reconcile_aap_with_git",
]
