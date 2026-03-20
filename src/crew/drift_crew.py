"""CrewAI Crew definition for AAP Drift Management."""

from typing import Any, Dict, List, Optional

from crewai import Crew, Process, Task

from src.agents import (
    create_git_reader_agent,
    create_aap_scanner_agent,
    create_drift_analyzer_agent,
    create_reconciler_agent,
)
from src.config import get_settings


class DriftManagementCrew:
    """CrewAI Crew for managing AAP configuration drift."""

    def __init__(
        self,
        object_types: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ):
        """Initialize the Drift Management Crew.
        
        Args:
            object_types: List of object types to manage. Defaults to settings.
            dry_run: Whether to run in dry-run mode. Defaults to settings.
        """
        settings = get_settings()
        self.object_types = object_types or settings.managed_object_types
        self.dry_run = dry_run if dry_run is not None else settings.dry_run
        
        # Create agents
        self.git_reader = create_git_reader_agent()
        self.aap_scanner = create_aap_scanner_agent()
        self.drift_analyzer = create_drift_analyzer_agent()
        self.reconciler = create_reconciler_agent()

    def _create_tasks(self) -> List[Task]:
        """Create the tasks for the drift management workflow."""
        object_types_str = ",".join(self.object_types)
        
        # Task 1: Read Git desired state
        read_git_task = Task(
            description=(
                f"Read all configuration files from the Git repository for the following "
                f"object types: {object_types_str}. Parse each YAML file and build a "
                f"complete picture of the desired state. Report the total number of "
                f"objects found for each type."
            ),
            expected_output=(
                "A summary of all objects found in Git for each object type, including "
                "the object names and their key configuration values."
            ),
            agent=self.git_reader,
        )
        
        # Task 2: Scan AAP current state
        scan_aap_task = Task(
            description=(
                f"Connect to the AAP instance and fetch all objects for the following "
                f"types: {object_types_str}. Build a complete inventory of what currently "
                f"exists in AAP. Report the total number of objects found for each type."
            ),
            expected_output=(
                "A summary of all objects found in AAP for each object type, including "
                "the object names, IDs, and their current configuration."
            ),
            agent=self.aap_scanner,
        )
        
        # Task 3: Analyze drift
        analyze_drift_task = Task(
            description=(
                f"Compare the Git desired state with the AAP current state for these "
                f"object types: {object_types_str}. Identify:\n"
                f"1. EXTRA objects: Exist in AAP but not defined in Git\n"
                f"2. MISSING objects: Defined in Git but don't exist in AAP\n"
                f"3. MODIFIED objects: Exist in both but have different configurations\n\n"
                f"For modified objects, list exactly which fields are different and "
                f"what the values are in Git vs AAP."
            ),
            expected_output=(
                "A detailed drift report listing all extra, missing, and modified objects. "
                "For modified objects, include the specific field differences."
            ),
            agent=self.drift_analyzer,
            context=[read_git_task, scan_aap_task],
        )
        
        # Task 4: Reconcile drift
        mode_str = "DRY-RUN MODE - report what would change" if self.dry_run else "APPLY changes"
        reconcile_task = Task(
            description=(
                f"Review the drift report and {mode_str}. For each drifted object:\n"
                f"- EXTRA objects: Delete them from AAP (unless protected)\n"
                f"- MISSING objects: Create them in AAP with the Git definition\n"
                f"- MODIFIED objects: Update them in AAP to match Git definition\n\n"
                f"{'Since this is a dry run, do NOT actually make changes. Just report ' if self.dry_run else ''}"
                f"{'what would be done.' if self.dry_run else 'Apply each change and verify it succeeded.'}"
            ),
            expected_output=(
                f"A reconciliation report showing {'what would be changed' if self.dry_run else 'what was changed'}. "
                f"Include success/failure status for each action."
            ),
            agent=self.reconciler,
            context=[analyze_drift_task],
        )
        
        return [read_git_task, scan_aap_task, analyze_drift_task, reconcile_task]

    def create_crew(self) -> Crew:
        """Create and return the CrewAI Crew."""
        return Crew(
            agents=[
                self.git_reader,
                self.aap_scanner,
                self.drift_analyzer,
                self.reconciler,
            ],
            tasks=self._create_tasks(),
            process=Process.sequential,
            verbose=True,
        )

    def run(self) -> Dict[str, Any]:
        """Run the drift management workflow.
        
        Returns:
            Dictionary containing the workflow results.
        """
        crew = self.create_crew()
        result = crew.kickoff()
        
        return {
            "object_types": self.object_types,
            "dry_run": self.dry_run,
            "result": result,
        }


def run_drift_management(
    object_types: Optional[List[str]] = None,
    dry_run: Optional[bool] = None,
) -> Dict[str, Any]:
    """Convenience function to run drift management.
    
    Args:
        object_types: List of object types to manage.
        dry_run: Whether to run in dry-run mode.
    
    Returns:
        Dictionary containing the workflow results.
    """
    crew = DriftManagementCrew(object_types=object_types, dry_run=dry_run)
    return crew.run()
