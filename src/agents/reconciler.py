"""Reconciler Agent - Applies changes to sync AAP with Git."""

from crewai import Agent

from src.config import get_maas_llm
from src.tools import (
    create_aap_object,
    update_aap_object,
    delete_aap_object,
    get_aap_object,
)


def create_reconciler_agent() -> Agent:
    """Create the Reconciler Agent.
    
    This agent is responsible for:
    - Reviewing the drift report
    - Deciding on appropriate actions
    - Applying changes to bring AAP in sync with Git
    - Verifying changes were successful
    """
    return Agent(
        role="AAP Reconciler",
        goal=(
            "Take the drift report and apply the necessary changes to bring AAP "
            "in sync with the Git definitions. Create missing objects, update "
            "modified objects to match their desired configuration, and delete "
            "extra objects that shouldn't exist. Ensure all changes are applied "
            "safely and verify the final state."
        ),
        backstory=(
            "You are an expert at reconciling infrastructure state with desired "
            "configurations. You understand the order of operations required when "
            "making changes to AAP - for example, organizations must exist before "
            "projects, and projects before job templates. You are careful and "
            "methodical, always verifying that changes have been applied correctly. "
            "You respect protected objects and never delete them. In dry-run mode, "
            "you report what would be changed without actually making changes."
        ),
        tools=[
            create_aap_object,
            update_aap_object,
            delete_aap_object,
            get_aap_object,
        ],
        llm=get_maas_llm(),
        verbose=True,
        allow_delegation=False,
    )
