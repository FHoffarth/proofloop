"""Planner: turns a problem statement into a claim set.

The claim set comes from the workflow profile, not from the model. The model
is asked only for a note; it cannot invent evidence requirements it would then
be able to satisfy on its own.
"""

from __future__ import annotations

from typing import Any

from ..profiles import get_profile
from ..providers import Provider, ProviderError
from ..schemas import Plan

PROMPT = (
    "You are a planner in an evidence-first pipeline.\n"
    "Problem: {problem}\n"
    "Profile: {profile}\n"
    "The deterministic claim set is fixed by the profile. "
    "Respond with a short note about what to watch out for."
)


class Planner:
    role = "planner"

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def plan(self, problem: str, profile_name: str, params: dict[str, Any]) -> Plan:
        profile = get_profile(profile_name)
        claims = profile.claims(params)
        notes = [f"profile: {profile.name} - {profile.description}"]

        response = self.provider.generate(
            PROMPT.format(problem=problem, profile=profile.name),
            role=self.role,
        )
        notes.append(f"planner note: {response.text}")

        return Plan(problem=problem, profile=profile.name, claims=claims, notes=notes)
