"""Agent roster.

Agents are instantiated once and reused across runs — they are stateless with
respect to incidents (all per-incident state lives in ``AgentContext``), so
sharing them avoids rebuilding tool registries and model clients per request.
"""

from __future__ import annotations

from functools import lru_cache

from app.agents.allocation import AllocationAgent
from app.agents.base import AgentContext, BaseAgent
from app.agents.commander import CommanderAgent
from app.agents.communication import CommunicationAgent
from app.agents.infrastructure import InfrastructureAgent
from app.agents.knowledge import KnowledgeAgent
from app.agents.medical import MedicalAgent
from app.agents.reflection import ReflectionAgent
from app.agents.shelter import ShelterAgent
from app.agents.situation import SituationAnalysisAgent
from app.agents.weather import WeatherAgent
from app.schemas.enums import AgentRole


@lru_cache
def get_agents() -> dict[AgentRole, BaseAgent]:
    """Singleton roster keyed by role."""
    roster: list[BaseAgent] = [
        SituationAnalysisAgent(),
        CommanderAgent(),
        WeatherAgent(),
        InfrastructureAgent(),
        MedicalAgent(),
        ShelterAgent(),
        KnowledgeAgent(),
        AllocationAgent(),
        ReflectionAgent(),
        CommunicationAgent(),
    ]
    return {agent.role: agent for agent in roster}


def get_agent(role: AgentRole) -> BaseAgent:
    agents = get_agents()
    if role not in agents:
        raise KeyError(f"No agent registered for role {role}")
    return agents[role]


__all__ = [
    "AgentContext",
    "AllocationAgent",
    "BaseAgent",
    "CommanderAgent",
    "CommunicationAgent",
    "InfrastructureAgent",
    "KnowledgeAgent",
    "MedicalAgent",
    "ReflectionAgent",
    "ShelterAgent",
    "SituationAnalysisAgent",
    "WeatherAgent",
    "get_agent",
    "get_agents",
]
