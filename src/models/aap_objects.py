"""AAP object metadata: endpoints, CaaC file map, dependency map, ignored fields."""

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


# ── Object type constants ──────────────────────────────────────────────────────

class ObjectType:
    ORGANIZATION = "organizations"
    CREDENTIAL_TYPE = "credential_types"
    EXECUTION_ENVIRONMENT = "execution_environments"
    PROJECT = "projects"
    INVENTORY = "inventories"
    CREDENTIAL = "credentials"
    JOB_TEMPLATE = "job_templates"
    WORKFLOW_JOB_TEMPLATE = "workflow_job_templates"
    TEAM = "teams"


# ── API endpoints ──────────────────────────────────────────────────────────────

_API = "/api/controller/v2"   # AAP 2.5+ uses /api/controller/v2/ (not /api/v2/)

OBJECT_TYPE_ENDPOINTS: Dict[str, str] = {
    ObjectType.ORGANIZATION:          f"{_API}/organizations/",
    ObjectType.CREDENTIAL_TYPE:       f"{_API}/credential_types/",
    ObjectType.EXECUTION_ENVIRONMENT: f"{_API}/execution_environments/",
    ObjectType.PROJECT:               f"{_API}/projects/",
    ObjectType.INVENTORY:             f"{_API}/inventories/",
    ObjectType.CREDENTIAL:            f"{_API}/credentials/",
    ObjectType.JOB_TEMPLATE:          f"{_API}/job_templates/",
    ObjectType.WORKFLOW_JOB_TEMPLATE: f"{_API}/workflow_job_templates/",
    ObjectType.TEAM:                  f"{_API}/teams/",
}


# ── CaaC → agent mapping ───────────────────────────────────────────────────────
# Each entry maps an object-type name to:
#   "file"  – filename inside group_vars/all/ in the git repo
#   "key"   – top-level YAML key containing the list of objects
#   "order" – creation order for reconciliation (lower = first)
#
# IMPORTANT: This repo uses inconsistent variable prefix conventions:
#   organizations  uses  "aap_organizations"   (NOT controller_organizations)
#   teams          uses  "aap_teams"           (NOT controller_teams)
#   job_templates  uses  "controller_templates" (NOT controller_job_templates)

CAAC_FILE_MAP: Dict[str, Dict[str, Any]] = {
    ObjectType.ORGANIZATION: {
        "file":  "organizations.yml",
        "key":   "aap_organizations",
        "order": 1,
    },
    ObjectType.CREDENTIAL_TYPE: {
        "file":  "credential_types.yml",
        "key":   "controller_credential_types",
        "order": 2,
    },
    ObjectType.EXECUTION_ENVIRONMENT: {
        "file":  "execution_environments.yml",
        "key":   "controller_execution_environments",
        "order": 3,
    },
    ObjectType.PROJECT: {
        "file":  "projects.yml",
        "key":   "controller_projects",
        "order": 4,
    },
    ObjectType.INVENTORY: {
        "file":  "inventories.yml",
        "key":   "controller_inventories",
        "order": 4,
    },
    ObjectType.CREDENTIAL: {
        "file":  "credentials.yml",
        "key":   "controller_credentials",
        "order": 5,
    },
    ObjectType.JOB_TEMPLATE: {
        "file":  "job_templates.yml",
        "key":   "controller_templates",
        "order": 6,
    },
    ObjectType.TEAM: {
        "file":  "teams.yml",
        "key":   "aap_teams",
        "order": 6,
    },
}

# Ordered list for dependency-safe reconciliation
MANAGED_OBJECT_ORDER: List[str] = sorted(
    CAAC_FILE_MAP.keys(), key=lambda k: CAAC_FILE_MAP[k]["order"]
)


# ── Dependency resolution map ──────────────────────────────────────────────────
# When creating objects via the API, name-valued fields must be resolved to IDs.
# Format: {object_type: {field_name: type_to_look_up}}

DEPENDENCY_FIELD_MAP: Dict[str, Dict[str, str]] = {
    ObjectType.ORGANIZATION: {
        # default_environment is optional — popped if EE doesn't exist yet
        "default_environment": ObjectType.EXECUTION_ENVIRONMENT,
    },
    ObjectType.EXECUTION_ENVIRONMENT: {
        # Pull-secret credential — optional; popped if credential not found yet
        "credential": ObjectType.CREDENTIAL,
    },
    ObjectType.PROJECT: {
        "organization":  ObjectType.ORGANIZATION,
        # scm_credential is renamed to "credential" by CAAC_TO_API_FIELD_MAP first,
        # then resolved here from name → ID (popped if credential not found)
        "credential":    ObjectType.CREDENTIAL,
    },
    ObjectType.INVENTORY: {
        "organization": ObjectType.ORGANIZATION,
    },
    ObjectType.CREDENTIAL: {
        "organization":    ObjectType.ORGANIZATION,
        "credential_type": ObjectType.CREDENTIAL_TYPE,
    },
    ObjectType.JOB_TEMPLATE: {
        "organization":          ObjectType.ORGANIZATION,
        "project":               ObjectType.PROJECT,
        "inventory":             ObjectType.INVENTORY,
        "execution_environment": ObjectType.EXECUTION_ENVIRONMENT,
    },
    ObjectType.TEAM: {
        "organization": ObjectType.ORGANIZATION,
    },
}

# Fields that are *lists* of names and must be associated via a sub-endpoint
# Format: {object_type: {field_name: (type_to_look_up, sub_endpoint_template)}}
ASSOCIATION_FIELD_MAP: Dict[str, Dict[str, Tuple[str, str]]] = {
    ObjectType.JOB_TEMPLATE: {
        "credentials": (
            ObjectType.CREDENTIAL,
            f"{_API}/job_templates/{{id}}/credentials/",
        ),
    },
    ObjectType.ORGANIZATION: {
        "galaxy_credentials": (
            ObjectType.CREDENTIAL,
            f"{_API}/organizations/{{id}}/galaxy_credentials/",
        ),
    },
}

# CaaC field names that differ from the AAP API field names
CAAC_TO_API_FIELD_MAP: Dict[str, Dict[str, str]] = {
    ObjectType.JOB_TEMPLATE: {
        "concurrent_jobs_enabled": "allow_simultaneous",
    },
    ObjectType.PROJECT: {
        # controller_configuration collection uses "scm_credential";
        # AAP API /projects/ endpoint uses "credential"
        "scm_credential": "credential",
    },
}

# CaaC-only fields that must be stripped before calling the AAP API
CAAC_STRIP_FIELDS: Dict[str, List[str]] = {
    ObjectType.PROJECT: ["update_project", "wait"],
    "_all": [
        "controller_configuration_projects_async_delay",
        "controller_configuration_credentials_secure_logging",
    ],
}


# ── Fields ignored during drift comparison ─────────────────────────────────────

IGNORED_FIELDS = {
    "id", "type", "url", "related", "summary_fields",
    "created", "modified",
    "last_job_run", "last_job_failed", "next_job_run",
    "status", "current_job",
    "last_update_failed", "last_updated",
    "scm_revision", "playbook_files",
    "custom_virtualenv",
    "inputs",     # credential secrets — never compared
    "managed",    # built-in flag on credential_types
}


# ── Lightweight Pydantic models ────────────────────────────────────────────────

class AAPObjectBase(BaseModel):
    name: str
    description: Optional[str] = ""

    class Config:
        extra = "allow"


class Organization(AAPObjectBase):
    max_hosts: Optional[int] = 0
    default_environment: Optional[str] = None


class Project(AAPObjectBase):
    organization: str
    scm_type: str = "git"
    scm_url: Optional[str] = None
    scm_branch: Optional[str] = "main"


class Inventory(AAPObjectBase):
    organization: str


class Credential(AAPObjectBase):
    organization: Optional[str] = None
    credential_type: str
    inputs: Optional[Dict[str, Any]] = Field(default_factory=dict, exclude=True)


class JobTemplate(AAPObjectBase):
    project: str
    playbook: str
    job_type: str = "run"


class Team(AAPObjectBase):
    organization: str


OBJECT_TYPE_MODELS = {
    ObjectType.ORGANIZATION:    Organization,
    ObjectType.PROJECT:         Project,
    ObjectType.INVENTORY:       Inventory,
    ObjectType.CREDENTIAL:      Credential,
    ObjectType.JOB_TEMPLATE:    JobTemplate,
    ObjectType.TEAM:            Team,
}
