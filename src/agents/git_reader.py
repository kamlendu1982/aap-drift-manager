"""Git Reader Agent - Parses Config-as-Code definitions from Git."""

from crewai import Agent

from src.tools import (
    read_git_directory,
    parse_yaml_file,
    get_all_definitions,
    pull_git_latest,
    get_desired_state,
)


def create_git_reader_agent() -> Agent:
    """Create the Git Reader Agent.
    
    This agent is responsible for:
    - Reading the Git repository containing Config-as-Code definitions
    - Parsing YAML/JSON configuration files
    - Building a complete picture of the desired state
    """
    return Agent(
        role="Git Config Reader",
        goal=(
            "Read and parse all AAP object definitions from the Git repository. "
            "Build a complete understanding of the desired state as defined in "
            "the Config-as-Code files."
        ),
        backstory=(
            "You are an expert at reading and understanding infrastructure-as-code. "
            "You have deep knowledge of Ansible Automation Platform object structures "
            "including projects, job templates, inventories, credentials, and workflows. "
            "You can parse YAML files and understand the relationships between different "
            "AAP objects. Your job is to extract the desired state from Git and present "
            "it in a structured format for comparison with the live AAP instance."
        ),
        tools=[
            read_git_directory,
            parse_yaml_file,
            get_all_definitions,
            pull_git_latest,
            get_desired_state,
        ],
        verbose=True,
        allow_delegation=False,
    )
