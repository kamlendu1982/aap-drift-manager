"""Models for drift detection and reporting."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DriftType(str, Enum):
    """Types of drift detected."""
    EXTRA = "extra"       # Object exists in AAP but not in Git
    MISSING = "missing"   # Object exists in Git but not in AAP
    MODIFIED = "modified" # Object exists in both but with different values


class ActionType(str, Enum):
    """Types of reconciliation actions."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    SKIP = "skip"


class ActionStatus(str, Enum):
    """Status of a reconciliation action."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DRY_RUN = "dry_run"


class FieldDiff(BaseModel):
    """Represents a difference in a single field."""
    field_name: str
    git_value: Any
    aap_value: Any
    path: str = ""  # For nested fields, e.g., "extra_vars.key"

    def __str__(self) -> str:
        return f"{self.field_name}: {self.aap_value!r} → {self.git_value!r}"


class DriftedObject(BaseModel):
    """Represents a single object with detected drift."""
    object_type: str
    object_name: str
    drift_type: DriftType
    git_definition: Optional[Dict[str, Any]] = None
    aap_state: Optional[Dict[str, Any]] = None
    field_diffs: List[FieldDiff] = Field(default_factory=list)
    aap_id: Optional[int] = None

    @property
    def recommended_action(self) -> ActionType:
        """Get the recommended action for this drift."""
        if self.drift_type == DriftType.EXTRA:
            return ActionType.DELETE
        elif self.drift_type == DriftType.MISSING:
            return ActionType.CREATE
        else:
            return ActionType.UPDATE


class ReconciliationAction(BaseModel):
    """Represents an action taken or to be taken."""
    action_type: ActionType
    object_type: str
    object_name: str
    object_id: Optional[int] = None
    status: ActionStatus = ActionStatus.PENDING
    changes: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None

    def mark_success(self) -> None:
        """Mark action as successful."""
        self.status = ActionStatus.SUCCESS
        self.timestamp = datetime.now()

    def mark_failed(self, error: str) -> None:
        """Mark action as failed."""
        self.status = ActionStatus.FAILED
        self.error_message = error
        self.timestamp = datetime.now()

    def mark_dry_run(self) -> None:
        """Mark action as dry run (not executed)."""
        self.status = ActionStatus.DRY_RUN
        self.timestamp = datetime.now()


class DriftReport(BaseModel):
    """Complete drift report."""
    generated_at: datetime = Field(default_factory=datetime.now)
    git_repo_path: str
    git_branch: str
    aap_url: str
    dry_run: bool = True

    # Object counts
    git_object_count: int = 0
    aap_object_count: int = 0

    # Drifted objects by type
    extra_objects: List[DriftedObject] = Field(default_factory=list)
    missing_objects: List[DriftedObject] = Field(default_factory=list)
    modified_objects: List[DriftedObject] = Field(default_factory=list)

    # Actions taken
    actions: List[ReconciliationAction] = Field(default_factory=list)

    @property
    def total_drift_count(self) -> int:
        """Total number of drifted objects."""
        return len(self.extra_objects) + len(self.missing_objects) + len(self.modified_objects)

    @property
    def has_drift(self) -> bool:
        """Check if any drift was detected."""
        return self.total_drift_count > 0

    @property
    def successful_actions(self) -> int:
        """Count of successful actions."""
        return sum(1 for a in self.actions if a.status == ActionStatus.SUCCESS)

    @property
    def failed_actions(self) -> int:
        """Count of failed actions."""
        return sum(1 for a in self.actions if a.status == ActionStatus.FAILED)

    def add_extra(self, obj: DriftedObject) -> None:
        """Add an extra object (in AAP, not in Git)."""
        obj.drift_type = DriftType.EXTRA
        self.extra_objects.append(obj)

    def add_missing(self, obj: DriftedObject) -> None:
        """Add a missing object (in Git, not in AAP)."""
        obj.drift_type = DriftType.MISSING
        self.missing_objects.append(obj)

    def add_modified(self, obj: DriftedObject) -> None:
        """Add a modified object."""
        obj.drift_type = DriftType.MODIFIED
        self.modified_objects.append(obj)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the drift report."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "git_repo": self.git_repo_path,
            "aap_url": self.aap_url,
            "dry_run": self.dry_run,
            "counts": {
                "git_objects": self.git_object_count,
                "aap_objects": self.aap_object_count,
                "extra": len(self.extra_objects),
                "missing": len(self.missing_objects),
                "modified": len(self.modified_objects),
                "total_drift": self.total_drift_count,
            },
            "actions": {
                "total": len(self.actions),
                "successful": self.successful_actions,
                "failed": self.failed_actions,
            }
        }
