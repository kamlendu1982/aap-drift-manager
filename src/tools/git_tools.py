"""Git tools for reading Config-as-Code definitions."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from crewai.tools import tool
from git import Repo

from src.config import get_settings


class GitTools:
    """Tools for interacting with Git Config-as-Code repository."""

    def __init__(self, repo_path: Optional[str] = None, branch: Optional[str] = None):
        settings = get_settings()
        self.repo_path = Path(repo_path or settings.git_repo_path)
        self.branch = branch or settings.git_branch
        self._repo: Optional[Repo] = None

    @property
    def repo(self) -> Repo:
        """Get or initialize the Git repository."""
        if self._repo is None:
            self._repo = Repo(self.repo_path)
        return self._repo

    def ensure_branch(self) -> None:
        """Ensure we're on the correct branch."""
        if self.repo.active_branch.name != self.branch:
            self.repo.git.checkout(self.branch)

    def pull_latest(self) -> str:
        """Pull latest changes from remote."""
        self.ensure_branch()
        origin = self.repo.remote("origin")
        origin.pull()
        return f"Pulled latest from {self.branch}"

    def list_config_files(self, object_type: str) -> List[Path]:
        """List all config files for a given object type."""
        type_dir = self.repo_path / object_type
        if not type_dir.exists():
            return []
        
        files = []
        for ext in ["*.yaml", "*.yml", "*.json"]:
            files.extend(type_dir.glob(ext))
        return sorted(files)

    def parse_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a YAML file and return its contents."""
        with open(file_path, "r") as f:
            content = yaml.safe_load(f)
        return content or {}

    def get_all_definitions(self, object_type: str) -> Dict[str, Dict[str, Any]]:
        """Get all object definitions for a given type.
        
        Returns a dict mapping object name to its definition.
        """
        definitions = {}
        files = self.list_config_files(object_type)
        
        for file_path in files:
            try:
                content = self.parse_yaml_file(file_path)
                
                # Handle both single object and list of objects
                if isinstance(content, list):
                    for obj in content:
                        if "name" in obj:
                            definitions[obj["name"]] = obj
                elif isinstance(content, dict):
                    if "name" in content:
                        definitions[content["name"]] = content
                    # Handle nested structure (e.g., {object_type: [objects]})
                    elif object_type in content:
                        for obj in content[object_type]:
                            if "name" in obj:
                                definitions[obj["name"]] = obj
            except Exception as e:
                print(f"Error parsing {file_path}: {e}")
                continue
        
        return definitions

    def get_desired_state(self, object_types: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Get complete desired state for all specified object types.
        
        Returns a nested dict: {object_type: {object_name: definition}}
        """
        desired_state = {}
        for obj_type in object_types:
            desired_state[obj_type] = self.get_all_definitions(obj_type)
        return desired_state


# CrewAI Tool Functions
@tool("Read Git directory structure")
def read_git_directory(object_type: str) -> str:
    """List all configuration files for a given object type in the Git repository.
    
    Args:
        object_type: The type of AAP object (e.g., 'projects', 'job_templates')
    
    Returns:
        A list of file paths found for the object type.
    """
    git_tools = GitTools()
    files = git_tools.list_config_files(object_type)
    if not files:
        return f"No configuration files found for {object_type}"
    
    file_list = "\n".join(f"  - {f.name}" for f in files)
    return f"Found {len(files)} files for {object_type}:\n{file_list}"


@tool("Parse YAML configuration file")
def parse_yaml_file(file_path: str) -> str:
    """Parse a YAML configuration file and return its contents.
    
    Args:
        file_path: Path to the YAML file relative to repo root.
    
    Returns:
        The parsed YAML content as a formatted string.
    """
    git_tools = GitTools()
    full_path = git_tools.repo_path / file_path
    
    if not full_path.exists():
        return f"File not found: {file_path}"
    
    content = git_tools.parse_yaml_file(full_path)
    return yaml.dump(content, default_flow_style=False)


@tool("Get all definitions for object type")
def get_all_definitions(object_type: str) -> str:
    """Get all object definitions for a specific type from Git.
    
    Args:
        object_type: The type of AAP object (e.g., 'projects', 'job_templates')
    
    Returns:
        A summary of all definitions found.
    """
    git_tools = GitTools()
    definitions = git_tools.get_all_definitions(object_type)
    
    if not definitions:
        return f"No definitions found for {object_type}"
    
    summary = [f"Found {len(definitions)} {object_type}:"]
    for name, definition in definitions.items():
        desc = definition.get("description", "No description")[:50]
        summary.append(f"  - {name}: {desc}")
    
    return "\n".join(summary)


@tool("Pull latest Git changes")
def pull_git_latest() -> str:
    """Pull the latest changes from the Git repository.
    
    Returns:
        Status message about the pull operation.
    """
    git_tools = GitTools()
    try:
        return git_tools.pull_latest()
    except Exception as e:
        return f"Failed to pull: {e}"


@tool("Get complete desired state")
def get_desired_state(object_types: str) -> str:
    """Get the complete desired state for specified object types.
    
    Args:
        object_types: Comma-separated list of object types.
    
    Returns:
        Summary of desired state for all types.
    """
    git_tools = GitTools()
    types_list = [t.strip() for t in object_types.split(",")]
    desired_state = git_tools.get_desired_state(types_list)
    
    summary = ["Desired State Summary:"]
    for obj_type, definitions in desired_state.items():
        summary.append(f"\n{obj_type}: {len(definitions)} objects")
        for name in definitions:
            summary.append(f"  - {name}")
    
    return "\n".join(summary)
