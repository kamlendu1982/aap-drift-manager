"""Diff tools for comparing Git and AAP states."""

from typing import Any, Dict, List, Optional, Tuple

from crewai.tools import tool
from deepdiff import DeepDiff

from src.models import (
    DriftedObject,
    DriftReport,
    DriftType,
    FieldDiff,
    IGNORED_FIELDS,
)


class DiffTools:
    """Tools for comparing configuration states."""

    def __init__(self, ignored_fields: Optional[set] = None):
        self.ignored_fields = ignored_fields or IGNORED_FIELDS

    def normalize_object(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize an object for comparison by removing ignored fields."""
        normalized = {}
        for key, value in obj.items():
            if key in self.ignored_fields:
                continue
            # Handle nested dicts
            if isinstance(value, dict):
                normalized[key] = self.normalize_object(value)
            # Handle lists
            elif isinstance(value, list):
                normalized[key] = [
                    self.normalize_object(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                normalized[key] = value
        return normalized

    def compare_objects(
        self,
        git_obj: Dict[str, Any],
        aap_obj: Dict[str, Any],
    ) -> Tuple[bool, List[FieldDiff]]:
        """Compare two objects and return differences.
        
        Returns:
            Tuple of (are_equal, list_of_diffs)
        """
        git_normalized = self.normalize_object(git_obj)
        aap_normalized = self.normalize_object(aap_obj)
        
        diff = DeepDiff(
            aap_normalized,
            git_normalized,
            ignore_order=True,
            report_repetition=True,
        )
        
        if not diff:
            return True, []
        
        field_diffs = []
        
        # Values changed
        for path, change in diff.get("values_changed", {}).items():
            field_name = self._extract_field_name(path)
            field_diffs.append(FieldDiff(
                field_name=field_name,
                git_value=change["new_value"],
                aap_value=change["old_value"],
                path=path,
            ))
        
        # Items added (in git, not in aap)
        for path, value in diff.get("dictionary_item_added", {}).items():
            field_name = self._extract_field_name(path)
            field_diffs.append(FieldDiff(
                field_name=field_name,
                git_value=value,
                aap_value=None,
                path=path,
            ))
        
        # Items removed (in aap, not in git)
        for path, value in diff.get("dictionary_item_removed", {}).items():
            field_name = self._extract_field_name(path)
            field_diffs.append(FieldDiff(
                field_name=field_name,
                git_value=None,
                aap_value=value,
                path=path,
            ))
        
        # Type changes
        for path, change in diff.get("type_changes", {}).items():
            field_name = self._extract_field_name(path)
            field_diffs.append(FieldDiff(
                field_name=field_name,
                git_value=change["new_value"],
                aap_value=change["old_value"],
                path=path,
            ))
        
        return False, field_diffs

    def _extract_field_name(self, path: str) -> str:
        """Extract a readable field name from a DeepDiff path."""
        # Path format: root['field']['nested']
        parts = path.replace("root", "").replace("']['", ".").replace("['", "").replace("']", "")
        return parts.strip(".")

    def find_drift(
        self,
        git_state: Dict[str, Dict[str, Any]],
        aap_state: Dict[str, Dict[str, Any]],
        object_type: str,
    ) -> Tuple[List[DriftedObject], List[DriftedObject], List[DriftedObject]]:
        """Find drift between Git and AAP states.
        
        Returns:
            Tuple of (extra_objects, missing_objects, modified_objects)
        """
        git_names = set(git_state.keys())
        aap_names = set(aap_state.keys())
        
        extra = []  # In AAP but not in Git
        missing = []  # In Git but not in AAP
        modified = []  # In both but different
        
        # Find extra objects (in AAP, not in Git)
        for name in aap_names - git_names:
            extra.append(DriftedObject(
                object_type=object_type,
                object_name=name,
                drift_type=DriftType.EXTRA,
                aap_state=aap_state[name],
                aap_id=aap_state[name].get("id"),
            ))
        
        # Find missing objects (in Git, not in AAP)
        for name in git_names - aap_names:
            missing.append(DriftedObject(
                object_type=object_type,
                object_name=name,
                drift_type=DriftType.MISSING,
                git_definition=git_state[name],
            ))
        
        # Find modified objects (in both but different)
        for name in git_names & aap_names:
            are_equal, diffs = self.compare_objects(
                git_state[name],
                aap_state[name],
            )
            if not are_equal:
                modified.append(DriftedObject(
                    object_type=object_type,
                    object_name=name,
                    drift_type=DriftType.MODIFIED,
                    git_definition=git_state[name],
                    aap_state=aap_state[name],
                    field_diffs=diffs,
                    aap_id=aap_state[name].get("id"),
                ))
        
        return extra, missing, modified

    def generate_diff_summary(self, drifted_object: DriftedObject) -> str:
        """Generate a human-readable diff summary."""
        lines = [f"{drifted_object.object_type}/{drifted_object.object_name}:"]
        lines.append(f"  Drift Type: {drifted_object.drift_type.value}")
        
        if drifted_object.field_diffs:
            lines.append("  Changes:")
            for diff in drifted_object.field_diffs:
                lines.append(f"    - {diff}")
        
        return "\n".join(lines)


# CrewAI Tool Functions
@tool("Compare two objects")
def compare_objects(git_definition: str, aap_state: str) -> str:
    """Compare a Git definition with AAP state and identify differences.
    
    Args:
        git_definition: YAML string of the Git definition
        aap_state: YAML string of the AAP state
    
    Returns:
        Comparison result showing any differences.
    """
    import yaml
    
    diff_tools = DiffTools()
    
    try:
        git_obj = yaml.safe_load(git_definition)
        aap_obj = yaml.safe_load(aap_state)
        
        are_equal, diffs = diff_tools.compare_objects(git_obj, aap_obj)
        
        if are_equal:
            return "Objects are identical"
        
        lines = ["Differences found:"]
        for diff in diffs:
            lines.append(f"  - {diff}")
        
        return "\n".join(lines)
    except Exception as e:
        return f"Error comparing objects: {e}"


@tool("Find all drift")
def find_all_drift(object_types: str) -> str:
    """Find all drift between Git and AAP for specified object types.
    
    Args:
        object_types: Comma-separated list of object types
    
    Returns:
        Summary of all drift found.
    """
    from src.tools.git_tools import GitTools
    from src.tools.aap_tools import AAPClient
    
    diff_tools = DiffTools()
    git_tools = GitTools()
    aap_client = AAPClient()
    
    types_list = [t.strip() for t in object_types.split(",")]
    
    try:
        all_extra = []
        all_missing = []
        all_modified = []
        
        for obj_type in types_list:
            git_state = git_tools.get_all_definitions(obj_type)
            aap_objects = aap_client.list_objects(obj_type)
            aap_state = {obj["name"]: obj for obj in aap_objects}
            
            extra, missing, modified = diff_tools.find_drift(
                git_state, aap_state, obj_type
            )
            
            all_extra.extend(extra)
            all_missing.extend(missing)
            all_modified.extend(modified)
        
        lines = ["Drift Analysis Results:", "=" * 50]
        
        if all_extra:
            lines.append(f"\nEXTRA OBJECTS ({len(all_extra)}) - In AAP, not in Git:")
            for obj in all_extra:
                lines.append(f"  - {obj.object_type}/{obj.object_name}")
        
        if all_missing:
            lines.append(f"\nMISSING OBJECTS ({len(all_missing)}) - In Git, not in AAP:")
            for obj in all_missing:
                lines.append(f"  - {obj.object_type}/{obj.object_name}")
        
        if all_modified:
            lines.append(f"\nMODIFIED OBJECTS ({len(all_modified)}):")
            for obj in all_modified:
                lines.append(f"  - {obj.object_type}/{obj.object_name}")
                for diff in obj.field_diffs:
                    lines.append(f"      {diff}")
        
        if not (all_extra or all_missing or all_modified):
            lines.append("\nNo drift detected! AAP is in sync with Git.")
        
        lines.append("=" * 50)
        total = len(all_extra) + len(all_missing) + len(all_modified)
        lines.append(f"Summary: {len(all_extra)} extra, {len(all_missing)} missing, {len(all_modified)} modified")
        
        return "\n".join(lines)
    except Exception as e:
        return f"Error finding drift: {e}"


@tool("Generate drift report")
def generate_drift_report(object_types: str) -> str:
    """Generate a complete drift report for specified object types.
    
    Args:
        object_types: Comma-separated list of object types
    
    Returns:
        Full drift report in structured format.
    """
    import json
    from src.config import get_settings
    from src.tools.git_tools import GitTools
    from src.tools.aap_tools import AAPClient
    
    settings = get_settings()
    diff_tools = DiffTools()
    git_tools = GitTools()
    aap_client = AAPClient()
    
    types_list = [t.strip() for t in object_types.split(",")]
    
    report = DriftReport(
        git_repo_path=str(git_tools.repo_path),
        git_branch=git_tools.branch,
        aap_url=aap_client.base_url,
        dry_run=settings.dry_run,
    )
    
    try:
        for obj_type in types_list:
            git_state = git_tools.get_all_definitions(obj_type)
            report.git_object_count += len(git_state)
            
            aap_objects = aap_client.list_objects(obj_type)
            aap_state = {obj["name"]: obj for obj in aap_objects}
            report.aap_object_count += len(aap_state)
            
            extra, missing, modified = diff_tools.find_drift(
                git_state, aap_state, obj_type
            )
            
            for obj in extra:
                report.add_extra(obj)
            for obj in missing:
                report.add_missing(obj)
            for obj in modified:
                report.add_modified(obj)
        
        return json.dumps(report.get_summary(), indent=2)
    except Exception as e:
        return f"Error generating report: {e}"
