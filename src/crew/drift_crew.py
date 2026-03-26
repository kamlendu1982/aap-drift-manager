"""CrewAI Crew definition for AAP Drift Management."""

from typing import Any, Dict, List, Optional

from crewai import Crew, Process, Task

from src.agents import (
    create_aap_scanner_agent,
    create_drift_analyzer_agent,
    create_git_reader_agent,
    create_reconciler_agent,
)
from src.config import get_settings
from src.models import MANAGED_OBJECT_ORDER


class DriftManagementCrew:
    """CrewAI Crew for managing AAP configuration drift.

    Workflow (4 sequential agents):
      1. Git CaaC Reader   – reads group_vars/all/ and builds desired state
      2. AAP State Scanner – queries AAP API and builds current state
      3. Drift Analyzer    – compares desired vs current, produces drift report
      4. Reconciler        – creates/updates/deletes in AAP to match Git
    """

    def __init__(
        self,
        object_types: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ):
        settings = get_settings()
        self.object_types = object_types or settings.managed_object_types
        self.dry_run = dry_run if dry_run is not None else settings.dry_run

        self.git_reader = create_git_reader_agent()
        self.aap_scanner = create_aap_scanner_agent()
        self.drift_analyzer = create_drift_analyzer_agent()
        self.reconciler = create_reconciler_agent()

    def _create_tasks(self) -> List[Task]:
        """Create the sequential tasks for the drift management workflow."""
        object_types_str = ", ".join(self.object_types)

        # ── Task 1: Read Git desired state ────────────────────────────────────
        read_git_task = Task(
            description=(
                f"Read the complete desired state from the Git Config-as-Code repository.\n\n"
                f"IMPORTANT - Repository layout:\n"
                f"  All config lives under: group_vars/all/\n"
                f"  Each object type has its own file with a specific YAML key:\n"
                f"    organizations.yml     → key: aap_organizations\n"
                f"    credential_types.yml  → key: controller_credential_types\n"
                f"    execution_environments.yml → key: controller_execution_environments\n"
                f"    projects.yml          → key: controller_projects\n"
                f"    inventories.yml       → key: controller_inventories\n"
                f"    credentials.yml       → key: controller_credentials\n"
                f"    job_templates.yml     → key: controller_templates\n"
                f"    teams.yml             → key: aap_teams\n\n"
                f"Start by calling 'Get full CaaC desired state' to see everything at once.\n"
                f"Then call 'Get all definitions for object type' for each type in this order:\n"
                f"{', '.join(MANAGED_OBJECT_ORDER)}\n\n"
                f"Report the name and count of every object found for each type."
            ),
            expected_output=(
                "A complete inventory of all objects defined in Git, grouped by type "
                "and listed in dependency order (organizations first, then credential_types, "
                "projects, inventories, credentials, job_templates, teams). "
                "Show the name of each object."
            ),
            agent=self.git_reader,
        )

        # ── Task 2: Scan AAP current state ────────────────────────────────────
        scan_aap_task = Task(
            description=(
                f"Query the AAP Controller API and get the current state for these object types:\n"
                f"{object_types_str}\n\n"
                f"Use 'Get AAP current state' with the full comma-separated list first, "
                f"then use 'List AAP objects' for each type individually to get details.\n\n"
                f"IMPORTANT for credential_types: only custom (non-built-in) types will be "
                f"returned — built-in types like 'Machine', 'Vault' are automatically filtered out.\n\n"
                f"Report the name and count of every object found for each type."
            ),
            expected_output=(
                "A complete inventory of all objects currently in AAP, grouped by type. "
                "Include the name and ID of each object."
            ),
            agent=self.aap_scanner,
        )

        # ── Task 3: Analyze drift ─────────────────────────────────────────────
        analyze_drift_task = Task(
            description=(
                f"Compare the Git desired state with the AAP current state for these types:\n"
                f"{object_types_str}\n\n"
                f"Use 'Find all drift' to do the full comparison automatically.\n\n"
                f"Identify THREE categories of drift:\n"
                f"  1. EXTRA objects   – exist in AAP but NOT defined in Git → must be deleted\n"
                f"  2. MISSING objects – defined in Git but NOT in AAP → must be created\n"
                f"  3. MODIFIED objects – exist in both but configuration differs → must be updated\n\n"
                f"For modified objects, list the exact fields that differ and show "
                f"the Git value vs the AAP value.\n\n"
                f"Process types in dependency order: {', '.join(MANAGED_OBJECT_ORDER)}"
            ),
            expected_output=(
                "A detailed drift report listing:\n"
                "- All EXTRA objects (in AAP, not in Git) — candidates for deletion\n"
                "- All MISSING objects (in Git, not in AAP) — candidates for creation\n"
                "- All MODIFIED objects with specific field differences\n"
                "- A summary: X extra, Y missing, Z modified\n"
                "- Objects grouped and ordered by dependency (organizations first)"
            ),
            agent=self.drift_analyzer,
            context=[read_git_task, scan_aap_task],
        )

        # ── Task 4: Reconcile ─────────────────────────────────────────────────
        object_types_arg = ",".join(self.object_types)
        reconcile_task = Task(
            description=(
                f"Your ONLY job is to call the 'Reconcile AAP with Git' tool with:\n\n"
                f"  object_types = \"{object_types_arg}\"\n\n"
                f"Do NOT attempt to create, update, or delete objects yourself.\n"
                f"Do NOT fabricate results — only report what the tool returns.\n"
                f"Simply call the tool once and copy its output as your final answer.\n\n"
                f"The tool handles everything automatically:\n"
                f"  - Reads the current state from AAP API\n"
                f"  - Reads the desired state from Git (group_vars/all/)\n"
                f"  - Computes drift (extra / missing / modified)\n"
                f"  - {'Reports what WOULD change (DRY_RUN=true in .env — no changes applied)' if self.dry_run else 'Applies all changes in dependency order (organizations first, then projects/inventories, then credentials, then job_templates)'}\n"
                f"  - Returns a detailed reconciliation report\n\n"
                f"Call the 'Reconcile AAP with Git' tool NOW with object_types=\"{object_types_arg}\"."
            ),
            expected_output=(
                "The exact output from the 'Reconcile AAP with Git' tool, including:\n"
                "- Count of objects created / updated / deleted / skipped / errored\n"
                "- List of each action taken\n"
                "- Final summary"
            ),
            agent=self.reconciler,
            context=[analyze_drift_task],
        )

        return [read_git_task, scan_aap_task, analyze_drift_task, reconcile_task]

    def create_crew(self) -> Crew:
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
    """Convenience function to run drift management via CrewAI.

    Args:
        object_types: List of object types to manage (default: from .env).
        dry_run: True = report only, False = apply changes (default: from .env).
    """
    crew = DriftManagementCrew(object_types=object_types, dry_run=dry_run)
    return crew.run()
