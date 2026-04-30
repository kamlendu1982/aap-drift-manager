"""Configuration management for AAP Drift Manager."""

from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # AAP Configuration — accept both canonical names and the names used in .env
    aap_url: str = Field(
        ...,
        validation_alias=AliasChoices("aap_url", "aap_mcp_server_url"),
        description="AAP Controller URL",
    )
    aap_token: Optional[str] = Field(
        None,
        validation_alias=AliasChoices("aap_token", "aap_api_token"),
        description="AAP API Token",
    )
    aap_username: Optional[str] = Field(None, description="AAP Username")
    aap_password: Optional[str] = Field(None, description="AAP Password")
    aap_verify_ssl: bool = Field(False, description="Verify SSL certificates")
    aap_mcp_port: int = Field(
        443,
        description="Port for the AAP MCP domain servers (job_management, platform_configuration, etc.)",
    )

    # Git Configuration — accepts a local path OR a remote git URL
    git_repo_path: str = Field(..., description="Local path or remote URL to CaaC repo")
    git_branch: str = Field("main", description="Git branch to use")

    # MAAS LLM Configuration
    maas_api_key: str = Field(..., description="MAAS API Key")
    maas_api_base: str = Field(..., description="MAAS API Base URL")
    maas_model: str = Field(..., description="MAAS Model name to use")

    # Agent Behavior
    dry_run: bool = Field(True, description="Dry run mode")
    log_level: str = Field("INFO", description="Logging level")
    managed_objects: str = Field(
        # Ordered by dependency: orgs first, then credential_types, then the rest
        "organizations,credential_types,execution_environments,"
        "projects,inventories,credentials,job_templates,teams",
        description="Comma-separated list of object types to manage (in dependency order)",
    )

    # Safety Settings
    require_confirmation: bool = Field(
        True, description="Require confirmation for destructive actions"
    )
    max_deletions: int = Field(10, description="Maximum objects to delete in single run")
    protected_objects: str = Field(
        "", description="Comma-separated list of protected object names"
    )
    # Comma-separated object TYPES for which deletion is completely disabled.
    # Extra objects of these types found in AAP (but not in Git) are silently
    # kept rather than deleted.  Set in .env, e.g.:  NO_DELETE_TYPES=credentials
    no_delete_types: str = Field(
        "",
        description="Object types where deletion is always skipped (comma-separated)",
    )

    @field_validator("aap_url")
    @classmethod
    def validate_aap_url(cls, v: str) -> str:
        """Ensure AAP URL doesn't have trailing slash."""
        return v.rstrip("/")

    @field_validator("git_repo_path")
    @classmethod
    def validate_git_repo_path(cls, v: str) -> str:
        """Accept local paths or remote git URLs (git@... / https://...)."""
        if v.startswith("git@") or v.startswith("https://") or v.startswith("http://"):
            return v  # Remote URL — GitTools will clone it lazily
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
    def no_delete_type_list(self) -> List[str]:
        """Object types where deletion is always skipped (code-enforced guardrail)."""
        if not self.no_delete_types:
            return []
        return [t.strip() for t in self.no_delete_types.split(",") if t.strip()]

    @property
    def has_valid_auth(self) -> bool:
        """Check if valid authentication is configured."""
        return bool(self.aap_token) or (
            bool(self.aap_username) and bool(self.aap_password)
        )


def load_settings() -> Settings:
    """Load settings from environment and .env file."""
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
    """Return a CrewAI LLM pointed at the MaaS (OpenAI-compatible) endpoint.

    litellm (used internally by CrewAI) routes 'openai/<model>' through the
    standard OpenAI Python client.  Depending on the litellm version it may
    ignore the api_key/base_url kwargs on LLM() and fall back to reading the
    OPENAI_API_KEY / OPENAI_API_BASE environment variables instead.

    We set both the env vars AND the LLM() kwargs so the credentials are
    picked up regardless of which code path the installed litellm version uses.
    This project never uses the real OpenAI — these env vars simply tell
    litellm where to send requests and what token to use.
    """
    import os
    from crewai import LLM

    settings = get_settings()

    # Set the env vars litellm checks as a fallback (belt-and-suspenders).
    os.environ["OPENAI_API_KEY"] = settings.maas_api_key
    os.environ["OPENAI_API_BASE"] = settings.maas_api_base

    return LLM(
        model=f"openai/{settings.maas_model}",
        api_key=settings.maas_api_key,
        base_url=settings.maas_api_base,
    )
