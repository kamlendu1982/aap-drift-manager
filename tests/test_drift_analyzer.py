"""Tests for Diff tools."""

import pytest

from src.tools.diff_tools import DiffTools
from src.models import DriftType


class TestDiffTools:
    """Tests for DiffTools class."""
    
    @pytest.fixture
    def diff_tools(self):
        """Create a DiffTools instance."""
        return DiffTools()
    
    def test_normalize_object_removes_ignored_fields(self, diff_tools):
        """Test that ignored fields are removed during normalization."""
        obj = {
            "name": "Test",
            "description": "A test",
            "id": 123,
            "url": "/api/v2/test/123/",
            "created": "2024-01-01",
            "modified": "2024-01-02",
        }
        
        normalized = diff_tools.normalize_object(obj)
        
        assert "name" in normalized
        assert "description" in normalized
        assert "id" not in normalized
        assert "url" not in normalized
        assert "created" not in normalized
        assert "modified" not in normalized
    
    def test_compare_identical_objects(self, diff_tools):
        """Test comparing identical objects."""
        git_obj = {"name": "Test", "verbosity": 1}
        aap_obj = {"name": "Test", "verbosity": 1}
        
        are_equal, diffs = diff_tools.compare_objects(git_obj, aap_obj)
        
        assert are_equal is True
        assert len(diffs) == 0
    
    def test_compare_different_objects(self, diff_tools):
        """Test comparing different objects."""
        git_obj = {"name": "Test", "verbosity": 2}
        aap_obj = {"name": "Test", "verbosity": 1}
        
        are_equal, diffs = diff_tools.compare_objects(git_obj, aap_obj)
        
        assert are_equal is False
        assert len(diffs) == 1
        assert diffs[0].field_name == "verbosity"
        assert diffs[0].git_value == 2
        assert diffs[0].aap_value == 1
    
    def test_compare_with_extra_field_in_git(self, diff_tools):
        """Test comparing when Git has an extra field."""
        git_obj = {"name": "Test", "extra_field": "value"}
        aap_obj = {"name": "Test"}
        
        are_equal, diffs = diff_tools.compare_objects(git_obj, aap_obj)
        
        assert are_equal is False
        assert any(d.field_name == "extra_field" for d in diffs)
    
    def test_compare_ignores_id_fields(self, diff_tools):
        """Test that ID and other ignored fields are not compared."""
        git_obj = {"name": "Test", "verbosity": 1}
        aap_obj = {"name": "Test", "verbosity": 1, "id": 123, "url": "/api/"}
        
        are_equal, diffs = diff_tools.compare_objects(git_obj, aap_obj)
        
        assert are_equal is True
        assert len(diffs) == 0
    
    def test_compare_nested_objects(self, diff_tools):
        """Test comparing objects with nested dicts."""
        git_obj = {
            "name": "Test",
            "extra_vars": {"key1": "value1", "key2": "new_value"},
        }
        aap_obj = {
            "name": "Test",
            "extra_vars": {"key1": "value1", "key2": "old_value"},
        }
        
        are_equal, diffs = diff_tools.compare_objects(git_obj, aap_obj)
        
        assert are_equal is False
        assert len(diffs) >= 1
    
    def test_find_drift_extra_objects(self, diff_tools):
        """Test finding extra objects (in AAP, not in Git)."""
        git_state = {
            "Project A": {"name": "Project A"},
        }
        aap_state = {
            "Project A": {"name": "Project A"},
            "Project B": {"name": "Project B"},  # Extra
        }
        
        extra, missing, modified = diff_tools.find_drift(
            git_state, aap_state, "projects"
        )
        
        assert len(extra) == 1
        assert extra[0].object_name == "Project B"
        assert extra[0].drift_type == DriftType.EXTRA
        assert len(missing) == 0
        assert len(modified) == 0
    
    def test_find_drift_missing_objects(self, diff_tools):
        """Test finding missing objects (in Git, not in AAP)."""
        git_state = {
            "Project A": {"name": "Project A"},
            "Project B": {"name": "Project B"},  # Missing from AAP
        }
        aap_state = {
            "Project A": {"name": "Project A"},
        }
        
        extra, missing, modified = diff_tools.find_drift(
            git_state, aap_state, "projects"
        )
        
        assert len(extra) == 0
        assert len(missing) == 1
        assert missing[0].object_name == "Project B"
        assert missing[0].drift_type == DriftType.MISSING
        assert len(modified) == 0
    
    def test_find_drift_modified_objects(self, diff_tools):
        """Test finding modified objects."""
        git_state = {
            "Project A": {"name": "Project A", "scm_branch": "main"},
        }
        aap_state = {
            "Project A": {"name": "Project A", "scm_branch": "develop"},  # Different
        }
        
        extra, missing, modified = diff_tools.find_drift(
            git_state, aap_state, "projects"
        )
        
        assert len(extra) == 0
        assert len(missing) == 0
        assert len(modified) == 1
        assert modified[0].object_name == "Project A"
        assert modified[0].drift_type == DriftType.MODIFIED
        assert len(modified[0].field_diffs) >= 1
    
    def test_find_drift_all_types(self, diff_tools):
        """Test finding all types of drift at once."""
        git_state = {
            "Project A": {"name": "Project A", "scm_branch": "main"},  # Modified
            "Project C": {"name": "Project C"},  # Missing
        }
        aap_state = {
            "Project A": {"name": "Project A", "scm_branch": "develop"},
            "Project B": {"name": "Project B"},  # Extra
        }
        
        extra, missing, modified = diff_tools.find_drift(
            git_state, aap_state, "projects"
        )
        
        assert len(extra) == 1
        assert len(missing) == 1
        assert len(modified) == 1
        
        assert extra[0].object_name == "Project B"
        assert missing[0].object_name == "Project C"
        assert modified[0].object_name == "Project A"
    
    def test_generate_diff_summary(self, diff_tools):
        """Test generating human-readable diff summary."""
        from src.models import DriftedObject, FieldDiff
        
        drifted = DriftedObject(
            object_type="projects",
            object_name="Test Project",
            drift_type=DriftType.MODIFIED,
            field_diffs=[
                FieldDiff(field_name="scm_branch", git_value="main", aap_value="develop"),
                FieldDiff(field_name="verbosity", git_value=2, aap_value=1),
            ],
        )
        
        summary = diff_tools.generate_diff_summary(drifted)
        
        assert "Test Project" in summary
        assert "modified" in summary.lower()
        assert "scm_branch" in summary
