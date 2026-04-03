"""Reconciler Agent — applies changes to sync AAP with Git."""

from crewai import Agent

from src.config import get_maas_llm
from src.tools.reconcile_tool import reconcile_aap_with_git


def create_reconciler_agent() -> Agent:
    """Create the Reconciler Agent.

    This agent's ONLY job is to call the 'Reconcile AAP with Git' tool.
    All logic (reading Git, reading AAP, diffing, creating/updating/deleting)
    is handled inside that single tool to avoid LLM hallucination.
    """
    return Agent(
        role="AAP Reconciler",
        goal=(
            "Call the 'Reconcile AAP with Git' tool to apply the correct changes "
            "to AAP. This single tool handles everything: reading Git, reading AAP, "
            "computing drift, and applying changes in dependency order." 
            "just make sure that you are not deleting the secrets and credentials from AAP even if they are not in Git"
        ),
        backstory=(
            "You are a precise infrastructure reconciliation specialist. "
            "You know that the safest way to reconcile AAP with Git is to use a "
            "single, atomic tool that handles everything without any LLM decisions. "
            "Your ONLY job is to call 'Reconcile AAP with Git' with the correct "
            "object_types argument and report the result. "
            "You NEVER pretend changes were made — you always call the tool first "
            "and report exactly what the tool returns."
        ),
        tools=[reconcile_aap_with_git],
        llm=get_maas_llm(),
        verbose=True,
        allow_delegation=False,
    )
