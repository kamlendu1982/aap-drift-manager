"""Tests for Git tools."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.tools.git_tools import GitTools


@pytest.fixture
def temp_repo():
    """Create a temporary directory with sample config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Create directory structure
        (repo_path / "projects").mkdir()
        (repo_path / "job_templates").mkdir()
        (repo_path / "inventories").mkdir()
        
        # Create sample project
        project_data = {
            "name": "Test Project",
            "description": "A test project",
            "organization": "Default",
            "scm_type": "git",
            "scm_url": "https://github.com/test/repo.git",
            "scm_branch": "main",
        }
        with open(repo_path / "projects" / "test_project.yaml", "w") as f:
            yaml.dump(project_data, f)
        
        # Create sample job template
        jt_data = {
            "name": "Test Job Template",
            "description": "A test job template",
            "project": "Test Project",
            "playbook": "playbooks/test.yml",
            "inventory": "Test Inventory",
            "job_type": "run",
            "verbosity": 1,
        }
        with open(repo_path / "job_templates" / "test_jt.yaml", "w") as f:
            yaml.dump(jt_data, f)
        
        # Create sample inventory
        inv_data = {
            "name": "Test Inventory",
            "description": "A test inventory",
            "organization": "Default",
        }
        with open(repo_path / "inventories" / "test_inv.yaml", "w") as f:
            yaml.dump(inv_data, f)
        
        yield repo_path


class TestGitTools:
    """Tests for GitTools class."""
    
    def test_list_config_files(self, temp_repo):
        """Test listing configuration files."""
        git_tools = GitTools(repo_path=str(temp_repo))
        
        files = git_tools.list_config_files("projects")
        assert len(files) == 1
        assert files[0].name == "test_project.yaml"
    
    def test_list_config_files_empty_dir(self, temp_repo):
        """Test listing files in non-existent directory."""
        git_tools = GitTools(repo_path=str(temp_repo))
        
        files = git_tools.list_config_files("nonexistent")
        assert len(files) == 0
    
    def test_parse_yaml_file(self, temp_repo):
        """Test parsing a YAML file."""
        git_tools = GitTools(repo_path=str(temp_repo))
        
        content = git_tools.parse_yaml_file(temp_repo / "projects" / "test_project.yaml")
        
        assert content["name"] == "Test Project"
        assert content["scm_type"] == "git"
        assert content["organization"] == "Default"
    
    def test_get_all_definitions(self, temp_repo):
        """Test getting all definitions for an object type."""
        git_tools = GitTools(repo_path=str(temp_repo))
        
        definitions = git_tools.get_all_definitions("projects")
        
        assert "Test Project" in definitions
        assert definitions["Test Project"]["scm_type"] == "git"
    
    def test_get_desired_state(self, temp_repo):
        """Test getting complete desired state."""
        git_tools = GitTools(repo_path=str(temp_repo))
        
        state = git_tools.get_desired_state(["projects", "job_templates", "inventories"])
        
        assert "projects" in state
        assert "job_templates" in state
        assert "inventories" in state
        
        assert "Test Project" in state["projects"]
        assert "Test Job Template" in state["job_templates"]
        assert "Test Inventory" in state["inventories"]
    
    def test_get_all_definitions_list_format(self, temp_repo):
        """Test parsing files with list of objects."""
        # Create a file with multiple objects
        multi_data = [
            {"name": "Project A", "scm_type": "git"},
            {"name": "Project B", "scm_type": "git"},
        ]
        with open(temp_repo / "projects" / "multi.yaml", "w") as f:
            yaml.dump(multi_data, f)
        
        git_tools = GitTools(repo_path=str(temp_repo))
        definitions = git_tools.get_all_definitions("projects")
        
        assert "Project A" in definitions
        assert "Project B" in definitions
