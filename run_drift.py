#!/usr/bin/env python3
"""Simple entry point to run AAP Drift Management.

Usage (from the project root directory with venv active):
    python run_drift.py                    # dry-run, all managed object types
    python run_drift.py --apply            # actually apply changes
    python run_drift.py --objects projects # limit to specific types
"""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the Python path
sys.path.insert(0, str(Path(__file__).parent))


def main():
    parser = argparse.ArgumentParser(
        description="AAP Drift Manager – reconcile AAP with Config-as-Code in Git"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply changes (default: dry-run only)",
    )
    parser.add_argument(
        "--objects",
        type=str,
        default=None,
        help="Comma-separated object types to manage (default: from .env)",
    )
    args = parser.parse_args()

    dry_run = not args.apply
    object_types = [o.strip() for o in args.objects.split(",")] if args.objects else None

    print("=" * 60)
    print("AAP Drift Manager")
    print(f"  Mode       : {'DRY-RUN (no changes)' if dry_run else 'APPLY CHANGES'}")
    print(f"  Objects    : {object_types or 'from .env (managed_objects)'}")
    print("=" * 60)

    from src.crew import run_drift_management

    result = run_drift_management(object_types=object_types, dry_run=dry_run)

    print("\n" + "=" * 60)
    print("Drift management complete.")
    print("=" * 60)
    print(result.get("result", result))


if __name__ == "__main__":
    main()
