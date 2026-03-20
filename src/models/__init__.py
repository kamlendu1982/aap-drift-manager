"""Models package for AAP Drift Manager."""

from .aap_objects import (
    AAPObjectBase,
    Credential,
    Inventory,
    JobTemplate,
    ObjectType,
    Organization,
    Project,
    Team,
    WorkflowJobTemplate,
    IGNORED_FIELDS,
    OBJECT_TYPE_ENDPOINTS,
    OBJECT_TYPE_MODELS,
)
from .drift_report import (
    ActionStatus,
    ActionType,
    DriftedObject,
    DriftReport,
    DriftType,
    FieldDiff,
    ReconciliationAction,
)

__all__ = [
    # AAP Objects
    "AAPObjectBase",
    "Credential",
    "Inventory",
    "JobTemplate",
    "ObjectType",
    "Organization",
    "Project",
    "Team",
    "WorkflowJobTemplate",
    "IGNORED_FIELDS",
    "OBJECT_TYPE_ENDPOINTS",
    "OBJECT_TYPE_MODELS",
    # Drift Report
    "ActionStatus",
    "ActionType",
    "DriftedObject",
    "DriftReport",
    "DriftType",
    "FieldDiff",
    "ReconciliationAction",
]
