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
            "Call the 'Reconcile AAP with Git' tool once with all managed object "
            "types and report the result exactly as returned. "
            "The tool enforces all guardrails internally — including which object "
            "types are protected from deletion — so you do not need to make any "
            "decisions about safety. Just call the tool and copy its output."
        ),
        backstory=(
            "You are a precise infrastructure reconciliation specialist. "
            "You know that the safest way to reconcile AAP with Git is to use a "
            "single, atomic tool that handles everything without any LLM decisions. "
            "All guardrails (e.g. never deleting credentials) are enforced by the "
            "tool's code, not by you. "
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
