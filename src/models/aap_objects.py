"""Pydantic models for AAP objects."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ObjectType(str, Enum):
    """Supported AAP object types."""
    ORGANIZATION = "organizations"
    PROJECT = "projects"
    INVENTORY = "inventories"
    CREDENTIAL = "credentials"
    JOB_TEMPLATE = "job_templates"
    WORKFLOW_JOB_TEMPLATE = "workflow_job_templates"
    TEAM = "teams"
    SETTINGS = "settings"


class AAPObjectBase(BaseModel):
    """Base model for all AAP objects."""
    name: str
    description: Optional[str] = ""

    class Config:
        extra = "allow"


class Organization(AAPObjectBase):
    """Organization object."""
    max_hosts: Optional[int] = 0
    default_environment: Optional[str] = None


class Project(AAPObjectBase):
    """Project object."""
    organization: str
    scm_type: str = "git"
    scm_url: Optional[str] = None
    scm_branch: Optional[str] = "main"
    scm_credential: Optional[str] = None
    scm_clean: bool = False
    scm_delete_on_update: bool = False
    scm_update_on_launch: bool = False
    allow_override: bool = False
    default_environment: Optional[str] = None


class Inventory(AAPObjectBase):
    """Inventory object."""
    organization: str
    kind: str = ""
    host_filter: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    prevent_instance_group_fallback: bool = False


class Credential(AAPObjectBase):
    """Credential object (secrets not compared)."""
    organization: Optional[str] = None
    credential_type: str
    inputs: Optional[Dict[str, Any]] = Field(default_factory=dict, exclude=True)


class JobTemplate(AAPObjectBase):
    """Job Template object."""
    organization: Optional[str] = None
    project: str
    playbook: str
    inventory: Optional[str] = None
    credential: Optional[str] = None
    credentials: Optional[List[str]] = None
    job_type: str = "run"
    verbosity: int = 0
    forks: int = 0
    limit: Optional[str] = None
    extra_vars: Optional[Dict[str, Any]] = None
    job_tags: Optional[str] = None
    skip_tags: Optional[str] = None
    become_enabled: bool = False
    diff_mode: bool = False
    allow_simultaneous: bool = False
    use_fact_cache: bool = False
    host_config_key: Optional[str] = None
    ask_scm_branch_on_launch: bool = False
    ask_diff_mode_on_launch: bool = False
    ask_variables_on_launch: bool = False
    ask_limit_on_launch: bool = False
    ask_tags_on_launch: bool = False
    ask_skip_tags_on_launch: bool = False
    ask_job_type_on_launch: bool = False
    ask_verbosity_on_launch: bool = False
    ask_inventory_on_launch: bool = False
    ask_credential_on_launch: bool = False
    survey_enabled: bool = False
    webhook_service: Optional[str] = None
    webhook_credential: Optional[str] = None
    execution_environment: Optional[str] = None
    instance_groups: Optional[List[str]] = None
    labels: Optional[List[str]] = None


class WorkflowJobTemplate(AAPObjectBase):
    """Workflow Job Template object."""
    organization: Optional[str] = None
    inventory: Optional[str] = None
    limit: Optional[str] = None
    scm_branch: Optional[str] = None
    extra_vars: Optional[Dict[str, Any]] = None
    ask_inventory_on_launch: bool = False
    ask_scm_branch_on_launch: bool = False
    ask_limit_on_launch: bool = False
    ask_variables_on_launch: bool = False
    survey_enabled: bool = False
    allow_simultaneous: bool = False
    webhook_service: Optional[str] = None
    webhook_credential: Optional[str] = None
    labels: Optional[List[str]] = None


class Team(AAPObjectBase):
    """Team object."""
    organization: str


# Mapping of object types to their models
OBJECT_TYPE_MODELS = {
    ObjectType.ORGANIZATION: Organization,
    ObjectType.PROJECT: Project,
    ObjectType.INVENTORY: Inventory,
    ObjectType.CREDENTIAL: Credential,
    ObjectType.JOB_TEMPLATE: JobTemplate,
    ObjectType.WORKFLOW_JOB_TEMPLATE: WorkflowJobTemplate,
    ObjectType.TEAM: Team,
}


# API endpoints for each object type
OBJECT_TYPE_ENDPOINTS = {
    ObjectType.ORGANIZATION: "/api/v2/organizations/",
    ObjectType.PROJECT: "/api/v2/projects/",
    ObjectType.INVENTORY: "/api/v2/inventories/",
    ObjectType.CREDENTIAL: "/api/v2/credentials/",
    ObjectType.JOB_TEMPLATE: "/api/v2/job_templates/",
    ObjectType.WORKFLOW_JOB_TEMPLATE: "/api/v2/workflow_job_templates/",
    ObjectType.TEAM: "/api/v2/teams/",
    ObjectType.SETTINGS: "/api/v2/settings/",
}


# Fields to ignore when comparing objects (auto-generated, read-only, or sensitive)
IGNORED_FIELDS = {
    "id",
    "type",
    "url",
    "related",
    "summary_fields",
    "created",
    "modified",
    "last_job_run",
    "last_job_failed",
    "next_job_run",
    "status",
    "current_job",
    "last_update_failed",
    "last_updated",
    "scm_revision",
    "playbook_files",
    "custom_virtualenv",
    "inputs",  # Credential secrets
}
