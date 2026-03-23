"""Configuration management for AAP Drift Manager."""

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # AAP Configuration
    aap_url: str = Field(..., description="AAP Controller URL")
    aap_token: Optional[str] = Field(None, description="AAP API Token")
    aap_username: Optional[str] = Field(None, description="AAP Username")
    aap_password: Optional[str] = Field(None, description="AAP Password")
    aap_verify_ssl: bool = Field(True, description="Verify SSL certificates")

    # Git Configuration
    git_repo_path: str = Field(..., description="Path to Config-as-Code repo")
    git_branch: str = Field("main", description="Git branch to use")

    # MAAS LLM Configuration
    maas_api_key: str = Field(..., description="MAAS API Key")
    maas_api_base: str = Field(..., description="MAAS API Base URL")
    maas_model: str = Field(..., description="MAAS Model name to use")

    # Agent Behavior
    dry_run: bool = Field(True, description="Dry run mode")
    log_level: str = Field("INFO", description="Logging level")
    managed_objects: str = Field(
        "projects,job_templates,inventories,credentials",
        description="Comma-separated list of object types to manage"
    )

    # Safety Settings
    require_confirmation: bool = Field(True, description="Require confirmation for destructive actions")
    max_deletions: int = Field(10, description="Maximum objects to delete in single run")
    protected_objects: str = Field("", description="Comma-separated list of protected object names")

    @field_validator("aap_url")
    @classmethod
    def validate_aap_url(cls, v: str) -> str:
        """Ensure AAP URL doesn't have trailing slash."""
        return v.rstrip("/")

    @field_validator("git_repo_path")
    @classmethod
    def validate_git_repo_path(cls, v: str) -> str:
        """Ensure Git repo path exists."""
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Git repository path does not exist: {v}")
        return str(path.absolute())

    @property
    def managed_object_types(self) -> List[str]:
        """Get list of managed object types."""
        return [obj.strip() for obj in self.managed_objects.split(",") if obj.strip()]

    @property
    def protected_object_names(self) -> List[str]:
        """Get list of protected object names."""
        if not self.protected_objects:
            return []
        return [obj.strip() for obj in self.protected_objects.split(",") if obj.strip()]

    @property
    def has_valid_auth(self) -> bool:
        """Check if valid authentication is configured."""
        return bool(self.aap_token) or (bool(self.aap_username) and bool(self.aap_password))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_settings() -> Settings:
    """Load settings from environment and .env file."""
    # Load .env file if it exists
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)

    return Settings()


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def get_maas_llm():
    """Get the MAAS LLM instance configured for CrewAI agents.

    Returns:
        LLM instance configured with MAAS API settings.
    """
    from crewai import LLM

    settings = get_settings()

    return LLM(
        model=f"openai/{settings.maas_model}",
        api_key=settings.maas_api_key,
        base_url=settings.maas_api_base,
    )
