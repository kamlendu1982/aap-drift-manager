"""Git Reader Agent — reads CaaC definitions from group_vars/all/ in Git."""

from crewai import Agent

from src.config import get_maas_llm
from src.tools import (
    get_all_definitions,
    get_desired_state,
    get_full_desired_state,
    parse_yaml_file,
    pull_git_latest,
    read_git_directory,
)


def create_git_reader_agent() -> Agent:
    """Create the Git Reader Agent.

    This agent reads the Config-as-Code repository and builds a complete picture
    of the DESIRED state — i.e. what should exist in AAP according to Git.

    The repo layout is:
        group_vars/all/organizations.yml   → key: aap_organizations
        group_vars/all/credential_types.yml → key: controller_credential_types
        group_vars/all/projects.yml        → key: controller_projects
        group_vars/all/inventories.yml     → key: controller_inventories
        group_vars/all/credentials.yml     → key: controller_credentials
        group_vars/all/job_templates.yml   → key: controller_templates
        group_vars/all/teams.yml           → key: aap_teams
    """
    return Agent(
        role="Git CaaC Reader",
        goal=(
            "Read ALL object definitions from the Git Config-as-Code repository "
            "(group_vars/all/ directory). Build a complete picture of the desired "
            "state that AAP should match. Process objects in dependency order: "
            "organizations first, then credential_types, then projects/inventories/"
            "credentials, then job_templates and teams."
        ),
        backstory=(
            "You are an expert at reading Ansible Automation Platform Config-as-Code "
            "repositories that follow the redhat_cop.controller_configuration collection "
            "format. You know that all configuration lives under group_vars/all/ and "
            "that YAML variable names don't always match the object type: "
            "'aap_organizations' (not controller_organizations), "
            "'controller_templates' (not controller_job_templates), "
            "'aap_teams' (not controller_teams). "
            "You always use 'Get full CaaC desired state' first to see everything at once, "
            "then drill into specific types with 'Get all definitions for object type'."
        ),
        tools=[
            get_full_desired_state,
            get_all_definitions,
            get_desired_state,
            read_git_directory,
            parse_yaml_file,
            pull_git_latest,
        ],
        llm=get_maas_llm(),
        verbose=True,
        allow_delegation=False,
    )
