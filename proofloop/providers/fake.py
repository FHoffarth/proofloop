"""A deterministic, zero-network provider.

Used for the dry run, for the test-suite, and as the default provider of the
offline foundation. It never imports an SDK and never opens a socket.
"""

from __future__ import annotations

from typing import Any

from .base import Provider, ProviderResponse
from .errors import ProviderRefusal, ProviderTimeout

DEFAULT_RESPONSES: dict[str, str] = {
    "planner": "Plan derived from the selected profile; no extra claims proposed.",
    "critic": "Critique: deterministic claims are the ones that matter; keep them required.",
    "judge": "ABSTAIN - evidence is the authority here, not this verdict.",
}


class FakeProvider(Provider):
    """Canned outputs plus explicit failure simulation.

    Parameters
    ----------
    responses:
        Per-role canned text, merged over :data:`DEFAULT_RESPONSES`.
    simulate_timeout / simulate_refusal:
        Raise :class:`ProviderTimeout` / :class:`ProviderRefusal` instead of
        answering. ``fail_on_role`` narrows the simulation to one role.
    """

    name = "fake"

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default_response: str = "(fake provider response)",
        simulate_timeout: bool = False,
        simulate_refusal: bool = False,
        fail_on_role: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.responses = {**DEFAULT_RESPONSES, **(responses or {})}
        self.default_response = default_response
        self.simulate_timeout = simulate_timeout
        self.simulate_refusal = simulate_refusal
        self.fail_on_role = fail_on_role
        self.metadata: dict[str, Any] = {"offline": True, "network": False, **(metadata or {})}
        self.prompts: list[tuple[str, str]] = []

    def generate(self, prompt: str, role: str = "", **kwargs: Any) -> ProviderResponse:
        self.call_count += 1
        self.prompts.append((role, prompt))

        targeted = self.fail_on_role in (None, role)
        if self.simulate_timeout and targeted:
            raise ProviderTimeout(f"fake provider timed out on role {role or '?'}")
        if self.simulate_refusal and targeted:
            raise ProviderRefusal(f"fake provider refused role {role or '?'}")

        return ProviderResponse(
            text=self.responses.get(role, self.default_response),
            role=role,
            provider=self.name,
            metadata={**self.metadata, "call_index": self.call_count},
        )
