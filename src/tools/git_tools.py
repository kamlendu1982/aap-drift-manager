"""Git tools for reading Config-as-Code definitions from group_vars/all/."""

import hashlib
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from crewai.tools import tool
from git import Repo

from src.config import get_settings
from src.models import CAAC_FILE_MAP, MANAGED_OBJECT_ORDER


def _is_remote_url(path: str) -> bool:
    return path.startswith("git@") or path.startswith("https://") or path.startswith("http://")


class GitTools:
    """Read Config-as-Code definitions from a Git repository.

    The repository is expected to follow the redhat_cop.controller_configuration
    layout where all objects live under group_vars/all/, one YAML file per type.
    Each file contains a top-level key (e.g. 'controller_projects',
    'aap_organizations') that holds a list of object definitions.
    """

    # Directory inside the repo where CaaC files live
    CAAC_DIR = "group_vars/all"

    def __init__(self, repo_path: Optional[str] = None, branch: Optional[str] = None):
        settings = get_settings()
        raw_path = repo_path or settings.git_repo_path
        self.branch = branch or settings.git_branch
        self._repo: Optional[Repo] = None

        if _is_remote_url(raw_path):
            self.repo_path = self._clone_or_update(raw_path)
        else:
            self.repo_path = Path(raw_path)

    # ── repo management ────────────────────────────────────────────────────────

    def _clone_or_update(self, remote_url: str) -> Path:
        """Clone a remote repo to a temp dir, or pull latest if already cloned."""
        import os
        import shutil

        url_hash = hashlib.md5(remote_url.encode()).hexdigest()[:8]
        local_path = Path(tempfile.gettempdir()) / f"aap-drift-caac-{url_hash}"

        ssh_cmd = "ssh -o StrictHostKeyChecking=no -F /dev/null"
        env = {**os.environ, "GIT_SSH_COMMAND": ssh_cmd}

        if local_path.exists() and (local_path / ".git").exists():
            print(f"[git] Updating existing clone at {local_path} …")
            try:
                repo = Repo(local_path)
                with repo.git.custom_environment(**{"GIT_SSH_COMMAND": ssh_cmd}):
                    repo.git.fetch("origin")
                    repo.git.checkout(self.branch)
                    repo.git.reset("--hard", f"origin/{self.branch}")
                print(f"[git] Pulled latest from {self.branch}")
            except Exception as exc:
                print(f"[git] Warning: could not update repo: {exc}")
        else:
            if local_path.exists():
                shutil.rmtree(local_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"[git] Cloning {remote_url} → {local_path} …")
            Repo.clone_from(remote_url, str(local_path), branch=self.branch, env=env)
            print("[git] Clone complete.")

        return local_path

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            self._repo = Repo(self.repo_path)
        return self._repo

    def ensure_branch(self) -> None:
        if self.repo.active_branch.name != self.branch:
            self.repo.git.checkout(self.branch)

    def pull_latest(self) -> str:
        self.ensure_branch()
        self.repo.remote("origin").pull()
        return f"Pulled latest from {self.branch}"

    # ── CaaC reading ───────────────────────────────────────────────────────────

    @property
    def caac_dir(self) -> Path:
        """Absolute path to the group_vars/all directory."""
        return self.repo_path / self.CAAC_DIR

    def list_caac_files(self) -> List[Path]:
        """List all YAML files in group_vars/all/."""
        d = self.caac_dir
        if not d.exists():
            return []
        files: List[Path] = []
        for ext in ("*.yaml", "*.yml"):
            files.extend(d.glob(ext))
        return sorted(files)

    def list_config_files(self, object_type: str) -> List[Path]:
        """Return the single CaaC file for this object type (if it exists)."""
        info = CAAC_FILE_MAP.get(object_type)
        if not info:
            return []
        candidate = self.caac_dir / info["file"]
        return [candidate] if candidate.exists() else []

    def parse_yaml_file(self, file_path: Path) -> Any:
        with open(file_path, "r") as fh:
            return yaml.safe_load(fh) or {}

    def get_all_definitions(self, object_type: str) -> Dict[str, Dict[str, Any]]:
        """Return {object_name: definition} for all objects of *object_type* in Git.

        Reads from group_vars/all/<file> and extracts the list under the
        correct top-level YAML key (e.g. 'controller_projects', 'aap_teams').
        """
        info = CAAC_FILE_MAP.get(object_type)
        if not info:
            return {}

        file_path = self.caac_dir / info["file"]
        if not file_path.exists():
            return {}

        try:
            raw = self.parse_yaml_file(file_path)
        except Exception as exc:
            print(f"Error parsing {file_path}: {exc}")
            return {}

        yaml_key: str = info["key"]

        # Extract the list of objects under the expected top-level key
        objects = raw.get(yaml_key, [])
        if objects is None:
            objects = []

        # Build name → definition mapping
        definitions: Dict[str, Dict[str, Any]] = {}
        for obj in objects:
            if isinstance(obj, dict) and "name" in obj:
                definitions[obj["name"]] = obj

        return definitions

    def get_desired_state(
        self, object_types: List[str]
    ) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Return {object_type: {object_name: definition}} for all given types."""
        return {t: self.get_all_definitions(t) for t in object_types}

    def get_all_caac_objects(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Return the complete desired state for ALL managed object types."""
        return self.get_desired_state(MANAGED_OBJECT_ORDER)


# ── CrewAI Tool Functions ──────────────────────────────────────────────────────

@tool("Read Git CaaC structure")
def read_git_directory(object_type: str) -> str:
    """List configuration files for a given object type in the Git repository.

    The repo stores all objects under group_vars/all/, one file per type.

    Args:
        object_type: e.g. 'projects', 'job_templates', 'organizations'
    """
    git = GitTools()
    info = CAAC_FILE_MAP.get(object_type)
    if not info:
        supported = ", ".join(CAAC_FILE_MAP.keys())
        return f"Unknown object type '{object_type}'. Supported: {supported}"

    file_path = git.caac_dir / info["file"]
    if file_path.exists():
        return (
            f"CaaC file for {object_type}:\n"
            f"  Path : {file_path}\n"
            f"  Key  : {info['key']}\n"
            f"  Order: {info['order']} (reconciliation priority)"
        )
    return f"No CaaC file found for {object_type} (expected {file_path})"


@tool("Parse YAML configuration file")
def parse_yaml_file(file_path: str) -> str:
    """Parse a YAML file from the repo and return its contents.

    Args:
        file_path: Path relative to repo root (e.g. 'group_vars/all/projects.yml')
    """
    git = GitTools()
    full = git.repo_path / file_path
    if not full.exists():
        return f"File not found: {file_path}"
    content = git.parse_yaml_file(full)
    return yaml.dump(content, default_flow_style=False)


@tool("Get all definitions for object type")
def get_all_definitions(object_type: str) -> str:
    """Get all object definitions for a specific type from the Git CaaC repo.

    Reads from group_vars/all/<file> using the correct YAML key for this
    repository (e.g. 'controller_projects', 'aap_organizations').

    Args:
        object_type: e.g. 'projects', 'job_templates', 'organizations', 'credentials'
    """
    git = GitTools()
    definitions = git.get_all_definitions(object_type)

    if not definitions:
        info = CAAC_FILE_MAP.get(object_type, {})
        return (
            f"No definitions found for {object_type}.\n"
            f"Expected file : group_vars/all/{info.get('file', '?')}\n"
            f"Expected key  : {info.get('key', '?')}"
        )

    lines = [f"Found {len(definitions)} {object_type} in Git:"]
    for name, defn in definitions.items():
        desc = str(defn.get("description", ""))[:60]
        lines.append(f"  - {name}" + (f": {desc}" if desc else ""))
    return "\n".join(lines)


@tool("Pull latest Git changes")
def pull_git_latest() -> str:
    """Pull the latest changes from the Git repository."""
    git = GitTools()
    try:
        return git.pull_latest()
    except Exception as exc:
        return f"Failed to pull: {exc}"


@tool("Get complete desired state")
def get_desired_state(object_types: str) -> str:
    """Get the complete desired state for a comma-separated list of object types.

    Args:
        object_types: Comma-separated list, e.g. 'organizations,projects,job_templates'
    """
    git = GitTools()
    types_list = [t.strip() for t in object_types.split(",")]
    state = git.get_desired_state(types_list)

    lines = ["Desired State from Git (group_vars/all/):"]
    for obj_type, defs in state.items():
        info = CAAC_FILE_MAP.get(obj_type, {})
        lines.append(f"\n{obj_type} [{info.get('file', '?')} / key={info.get('key', '?')}]: {len(defs)} objects")
        for name in defs:
            lines.append(f"  - {name}")
    return "\n".join(lines)


@tool("Get full CaaC desired state")
def get_full_desired_state() -> str:
    """Get the complete desired state for ALL managed object types from Git.

    Processes objects in dependency order (organizations first, then credential
    types, projects, inventories, credentials, then job templates and teams).
    """
    git = GitTools()
    state = git.get_all_caac_objects()

    lines = ["Complete CaaC Desired State (dependency order):"]
    total = 0
    for obj_type in MANAGED_OBJECT_ORDER:
        defs = state.get(obj_type, {})
        info = CAAC_FILE_MAP.get(obj_type, {})
        lines.append(f"\n[{info.get('order')}] {obj_type} ({info.get('file','?')}): {len(defs)} objects")
        for name in defs:
            lines.append(f"  - {name}")
        total += len(defs)
    lines.append(f"\nTotal: {total} objects across {len(MANAGED_OBJECT_ORDER)} types")
    return "\n".join(lines)
