"""Critic: reviews the plan before any evidence is collected.

The critic may comment and may flag gaps, but it cannot delete a claim. A
model that could remove inconvenient claims would be able to talk its way
past the gate.
"""

from __future__ import annotations

from ..providers import Provider
from ..schemas import Critique, Plan

PROMPT = (
    "You are a critic in an evidence-first pipeline.\n"
    "Problem: {problem}\n"
    "Claims to be verified:\n{claims}\n"
    "Point out what this claim set would fail to catch."
)


class Critic:
    role = "critic"

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def review(self, plan: Plan) -> Critique:
        rendered = "\n".join(
            f"- {c.id} [{c.type.value}] required={c.required}: {c.statement}"
            for c in plan.claims
        ) or "- (no claims)"

        response = self.provider.generate(
            PROMPT.format(problem=plan.problem, claims=rendered),
            role=self.role,
        )

        notes = [f"critic note: {response.text}"]
        if not plan.claims:
            notes.append(
                "critic warning: no claims in this plan, so nothing can be proven."
            )
        if plan.claims and not any(c.deterministic and c.required for c in plan.claims):
            notes.append(
                "critic warning: no required deterministic claim - the gate has no facts to stand on."
            )
        return Critique(plan=plan, notes=notes)
