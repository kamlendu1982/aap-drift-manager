"""AAP Scanner Agent - Discovers live state from AAP instance."""

from crewai import Agent

from src.config import get_maas_llm
from src.tools import (
    list_aap_objects,
    get_aap_object,
    get_aap_current_state,
)


def create_aap_scanner_agent() -> Agent:
    """Create the AAP Scanner Agent.
    
    This agent is responsible for:
    - Connecting to the AAP instance via API
    - Fetching all objects of each type
    - Building a complete picture of the current state
    """
    return Agent(
        role="AAP State Scanner",
        goal=(
            "Connect to the Ansible Automation Platform and discover the current state "
            "of all managed objects. Build a complete inventory of projects, job templates, "
            "inventories, credentials, and other objects as they exist in AAP right now."
        ),
        backstory=(
            "You are an expert at interacting with the Ansible Automation Platform API. "
            "You understand the AAP object model and know how to efficiently query for "
            "all objects of each type. You can navigate pagination, resolve relationships "
            "between objects, and normalize API responses into a consistent format. "
            "Your job is to capture the exact current state of AAP for comparison."
        ),
        tools=[
            list_aap_objects,
            get_aap_object,
            get_aap_current_state,
        ],
        llm=get_maas_llm(),
        verbose=True,
        allow_delegation=False,
    )
