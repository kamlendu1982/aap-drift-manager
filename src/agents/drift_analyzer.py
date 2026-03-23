"""Drift Analyzer Agent - Compares states and detects drift."""

from crewai import Agent

from src.config import get_maas_llm
from src.tools import (
    compare_objects,
    find_all_drift,
    generate_drift_report,
)


def create_drift_analyzer_agent() -> Agent:
    """Create the Drift Analyzer Agent.
    
    This agent is responsible for:
    - Comparing Git definitions with AAP state
    - Identifying three types of drift:
      - Extra: Objects in AAP but not in Git
      - Missing: Objects in Git but not in AAP
      - Modified: Objects in both but with different configurations
    - Generating a detailed drift report
    """
    return Agent(
        role="Drift Analyzer",
        goal=(
            "Compare the desired state from Git with the current state in AAP. "
            "Identify all configuration drift including extra objects that shouldn't "
            "exist, missing objects that should be created, and modified objects "
            "that have been changed from their desired configuration."
        ),
        backstory=(
            "You are an expert at detecting configuration drift in infrastructure. "
            "You have a keen eye for detail and can identify even subtle differences "
            "between desired and actual states. You understand which fields are "
            "significant for comparison and which can be safely ignored (like IDs, "
            "timestamps, and auto-generated fields). You produce clear, actionable "
            "drift reports that help operations teams understand exactly what has "
            "changed and why it matters."
        ),
        tools=[
            compare_objects,
            find_all_drift,
            generate_drift_report,
        ],
        llm=get_maas_llm(),
        verbose=True,
        allow_delegation=False,
    )
