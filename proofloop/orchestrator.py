"""The pipeline.

    Planner -> Critic -> EvidenceVerifier -> PRE-GATE -> [Judge] -> FINAL GATE

If the pre-gate is BLOCKED the judge is not called: deterministic blockers
stop expensive reasoning early. Any provider failure fails closed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agents import Critic, Judge, Planner
from .evidence import UnsafePath
from .evidence.verifier import EvidenceVerifier
from .gate import ProofGate
from .profiles import ProfileError
from .providers import Provider, ProviderError
from .registry import get_provider
from .schemas import GateDecision, GateResult, Plan, RunReport


class Orchestrator:
    def __init__(
        self,
        repo: Path | str = ".",
        provider: Provider | None = None,
        use_judge: bool = True,
        test_timeout: int = 300,
    ) -> None:
        self.repo = Path(repo)
        self.provider = provider or get_provider("fake")
        self.use_judge = use_judge
        self.test_timeout = test_timeout
        self.gate = ProofGate()

    def run(self, problem: str, profile: str, params: dict[str, Any] | None = None) -> RunReport:
        params = params or {}
        errors: list[str] = []
        empty_plan = Plan(problem=problem, profile=profile)

        # --- setup ------------------------------------------------------
        try:
            verifier = EvidenceVerifier(self.repo, test_timeout=self.test_timeout)
        except UnsafePath as exc:
            return self._failed_run(problem, profile, empty_plan, [f"repo error: {exc}"])

        # --- planner ----------------------------------------------------
        try:
            plan = Planner(self.provider).plan(problem, profile, params)
        except ProfileError as exc:
            return self._failed_run(problem, profile, empty_plan, [f"profile error: {exc}"])
        except ProviderError as exc:
            return self._failed_run(
                problem, profile, empty_plan, [f"provider failed in planner: {exc}"]
            )

        # --- critic -----------------------------------------------------
        try:
            critique_notes = Critic(self.provider).review(plan).notes
        except ProviderError as exc:
            return self._failed_run(problem, profile, plan, [f"provider failed in critic: {exc}"])

        # --- evidence ---------------------------------------------------
        verified = verifier.verify_all(plan.claims)

        # --- pre-gate ---------------------------------------------------
        pre_gate = self.gate.evaluate(verified, errors)

        # --- judge (only if the pre-gate did not block) -----------------
        if pre_gate.result is GateResult.BLOCKED:
            judge_verdict = Judge.skipped(
                "pre-gate BLOCKED: deterministic blockers stop expensive reasoning early"
            )
        elif not self.use_judge:
            judge_verdict = Judge.skipped("judge disabled for this run")
        else:
            try:
                judge_verdict = Judge(self.provider).judge(verified)
            except ProviderError as exc:
                errors.append(f"provider failed in judge: {exc}")
                judge_verdict = Judge.skipped(f"provider error: {exc}")

        # --- final gate -------------------------------------------------
        # Re-evaluated from evidence alone. The judge verdict is reported,
        # never consulted.
        final_gate = self.gate.evaluate(verified, errors)

        return RunReport(
            problem=problem,
            profile=plan.profile,
            repo=str(self.repo),
            plan=plan,
            critique_notes=critique_notes,
            verified=verified,
            pre_gate=pre_gate,
            judge=judge_verdict,
            final_gate=final_gate,
            provider=getattr(self.provider, "name", "unknown"),
            provider_calls=getattr(self.provider, "call_count", 0),
            errors=errors,
        )

    def _failed_run(
        self, problem: str, profile: str, plan: Plan, errors: list[str]
    ) -> RunReport:
        """A pipeline failure is a BLOCKED run: missing evidence fails closed."""
        decision = GateDecision(
            result=GateResult.BLOCKED,
            reasons=[],
            blockers=list(errors),
            review_items=[],
        )
        return RunReport(
            problem=problem,
            profile=profile,
            repo=str(self.repo),
            plan=plan,
            critique_notes=[],
            verified=[],
            pre_gate=decision,
            judge=Judge.skipped("pipeline failed before the judge step"),
            final_gate=decision,
            provider=getattr(self.provider, "name", "unknown"),
            provider_calls=getattr(self.provider, "call_count", 0),
            errors=list(errors),
        )
