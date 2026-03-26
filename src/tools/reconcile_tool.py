"""Single atomic reconciliation tool — no LLM hallucination possible."""

import json
from typing import List, Optional

from crewai.tools import tool

from src.models import MANAGED_OBJECT_ORDER


def _http_detail(exc: Exception) -> str:
    """Return a concise error message including the API response body if available."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300]
        return f"{exc} | API response: {body}"
    return str(exc)


def _is_403(exc: Exception) -> bool:
    resp = getattr(exc, "response", None)
    return resp is not None and resp.status_code == 403


@tool("Reconcile AAP with Git")
def reconcile_aap_with_git(object_types: Optional[str] = None) -> str:
    """Run full drift detection AND reconciliation in a single call.

    This tool does EVERYTHING itself — no LLM decisions needed:
      1. Clone / pull the Git CaaC repo (group_vars/all/)
      2. Query AAP API for current state
      3. Compute drift (extra, missing, modified) per object type
      4. Apply changes in strict dependency order:
           organizations → credential_types → execution_environments
           → projects, inventories → credentials
           → job_templates, teams
      5. Return a detailed report of every action taken (or that would be taken
         in DRY RUN mode)

    Args:
        object_types: Comma-separated list of object types to reconcile.
                      Defaults to ALL managed types in dependency order.
                      Example: "organizations,projects,job_templates"
    """
    from src.config import get_settings
    from src.tools.git_tools import GitTools
    from src.tools.aap_tools import AAPClient
    from src.tools.diff_tools import DiffTools

    settings = get_settings()
    git = GitTools()
    aap = AAPClient()
    diff_tools = DiffTools()

    if object_types:
        types_list = [t.strip() for t in object_types.split(",")]
    else:
        types_list = MANAGED_OBJECT_ORDER

    # Only process types we know about
    types_list = [t for t in types_list if t in MANAGED_OBJECT_ORDER]

    report = {
        "dry_run": settings.dry_run,
        "created": [],
        "updated": [],
        "deleted": [],
        "skipped": [],
        "errors": [],
    }

    print(f"\n{'[DRY RUN] ' if settings.dry_run else ''}Reconciling {len(types_list)} object types …")

    for obj_type in types_list:
        print(f"\n── {obj_type} ──")

        # 1. Read desired state from Git
        try:
            git_state = git.get_all_definitions(obj_type)
            print(f"  Git: {len(git_state)} objects")
        except Exception as exc:
            msg = f"Failed to read {obj_type} from Git: {exc}"
            report["errors"].append(msg)
            print(f"  ERROR: {msg}")
            continue

        # 2. Read current state from AAP
        try:
            aap_objects = aap.list_objects(obj_type)
            aap_state = {o["name"]: o for o in aap_objects}
            print(f"  AAP: {len(aap_state)} objects")
        except Exception as exc:
            msg = f"Failed to read {obj_type} from AAP: {exc}"
            report["errors"].append(msg)
            print(f"  ERROR: {msg}")
            continue

        # 3. Compute drift
        extra, missing, modified = diff_tools.find_drift(git_state, aap_state, obj_type)
        print(f"  Drift → {len(extra)} extra, {len(missing)} missing, {len(modified)} modified")

        # 4a. Create MISSING objects
        for obj in missing:
            label = f"{obj_type}/{obj.object_name}"
            definition = git_state[obj.object_name]

            if settings.dry_run:
                msg = f"[DRY RUN] Would create {label}"
                report["skipped"].append(msg)
                print(f"  + {msg}")
                continue

            try:
                result = aap.create_object(obj_type, definition)
                msg = f"Created {label} (ID: {result.get('id')})"
                report["created"].append(msg)
                print(f"  ✓ {msg}")
            except Exception as exc:
                detail = _http_detail(exc)
                msg = f"Failed to create {label}: {detail}"
                report["errors"].append(msg)
                print(f"  ✗ {msg}")

        # 4b. Update MODIFIED objects
        for obj in modified:
            label = f"{obj_type}/{obj.object_name}"
            git_def = git_state[obj.object_name]

            if settings.dry_run:
                changes = ", ".join(str(d) for d in obj.field_diffs[:3])
                msg = f"[DRY RUN] Would update {label} ({changes})"
                report["skipped"].append(msg)
                print(f"  ~ {msg}")
                continue

            try:
                result = aap.update_object(obj_type, obj.aap_id, git_def)
                msg = f"Updated {label}"
                report["updated"].append(msg)
                print(f"  ✓ {msg}")
            except Exception as exc:
                detail = _http_detail(exc)
                msg = f"Failed to update {label}: {detail}"
                report["errors"].append(msg)
                print(f"  ✗ {msg}")

        # 4c. Delete EXTRA objects (if not protected)
        for obj in extra:
            label = f"{obj_type}/{obj.object_name}"

            if obj.object_name in settings.protected_object_names:
                msg = f"Skipped protected: {label}"
                report["skipped"].append(msg)
                print(f"  ⚠ {msg}")
                continue

            if settings.dry_run:
                msg = f"[DRY RUN] Would delete {label}"
                report["skipped"].append(msg)
                print(f"  - {msg}")
                continue

            try:
                success = aap.delete_object(obj_type, obj.aap_id)
                if success:
                    msg = f"Deleted {label}"
                    report["deleted"].append(msg)
                    print(f"  ✓ {msg}")
                else:
                    msg = f"Delete returned non-success for {label}"
                    report["errors"].append(msg)
                    print(f"  ✗ {msg}")
            except Exception as exc:
                if _is_403(exc):
                    msg = f"Skipped system/protected object (cannot delete): {label}"
                    report["skipped"].append(msg)
                    print(f"  ⚠ {msg}")
                else:
                    detail = _http_detail(exc)
                    msg = f"Failed to delete {label}: {detail}"
                    report["errors"].append(msg)
                    print(f"  ✗ {msg}")

    # ── Final summary ──────────────────────────────────────────────────────────
    mode = "DRY RUN — no changes applied" if settings.dry_run else "APPLIED"
    summary_lines = [
        "",
        f"{'=' * 60}",
        f"Reconciliation Complete [{mode}]",
        f"{'=' * 60}",
        f"  Created : {len(report['created'])}",
        f"  Updated : {len(report['updated'])}",
        f"  Deleted : {len(report['deleted'])}",
        f"  Skipped : {len(report['skipped'])}",
        f"  Errors  : {len(report['errors'])}",
    ]

    for category, items in [
        ("CREATED", report["created"]),
        ("UPDATED", report["updated"]),
        ("DELETED", report["deleted"]),
        ("ERRORS",  report["errors"]),
    ]:
        if items:
            summary_lines.append(f"\n{category}:")
            for item in items:
                summary_lines.append(f"  • {item}")

    if settings.dry_run:
        summary_lines.append(
            "\nTo apply these changes, set DRY_RUN=false in .env and run again."
        )

    return "\n".join(summary_lines)
