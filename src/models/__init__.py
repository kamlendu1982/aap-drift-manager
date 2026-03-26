"""Models package for AAP Drift Manager."""

from .aap_objects import (
    AAPObjectBase,
    ASSOCIATION_FIELD_MAP,
    CAAC_FILE_MAP,
    CAAC_STRIP_FIELDS,
    CAAC_TO_API_FIELD_MAP,
    Credential,
    DEPENDENCY_FIELD_MAP,
    IGNORED_FIELDS,
    Inventory,
    JobTemplate,
    MANAGED_OBJECT_ORDER,
    OBJECT_TYPE_ENDPOINTS,
    OBJECT_TYPE_MODELS,
    ObjectType,
    Organization,
    Project,
    Team,
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
    # AAP object metadata
    "AAPObjectBase",
    "ASSOCIATION_FIELD_MAP",
    "CAAC_FILE_MAP",
    "CAAC_STRIP_FIELDS",
    "CAAC_TO_API_FIELD_MAP",
    "Credential",
    "DEPENDENCY_FIELD_MAP",
    "IGNORED_FIELDS",
    "Inventory",
    "JobTemplate",
    "MANAGED_OBJECT_ORDER",
    "OBJECT_TYPE_ENDPOINTS",
    "OBJECT_TYPE_MODELS",
    "ObjectType",
    "Organization",
    "Project",
    "Team",
    # Drift report
    "ActionStatus",
    "ActionType",
    "DriftedObject",
    "DriftReport",
    "DriftType",
    "FieldDiff",
    "ReconciliationAction",
]
