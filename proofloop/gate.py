"""The ProofGate.

The gate is the only authority on whether work may proceed. A judge verdict
is advisory input to the report, never an override of this decision.

Rules, in order of precedence:

1. A required deterministic fact that FAILED, or that was never conclusively
   checked (INSUFFICIENT / NOT_CHECKED), is a blocker -> BLOCKED.
   Missing evidence fails closed.
2. Any claim that is not PROVEN but still open -- every evaluative claim, and
   any non-required deterministic claim that did not verify -> REVIEW_REQUIRED.
3. Otherwise -> PASS.
"""

from __future__ import annotations

from .schemas import (
    ConfidenceLevel,
    GateDecision,
    GateResult,
    VerificationResult,
    VerifiedClaim,
)

_CONCLUSIVE_FAILURES = {
    VerificationResult.FAILED,
    VerificationResult.INSUFFICIENT,
    VerificationResult.NOT_CHECKED,
}


class ProofGate:
    """Deterministic policy over verified claims."""

    def evaluate(
        self,
        verified: list[VerifiedClaim],
        errors: list[str] | None = None,
    ) -> GateDecision:
        blockers: list[str] = list(errors or [])
        review: list[str] = []
        reasons: list[str] = []

        for vc in verified:
            claim = vc.claim
            label = f"{claim.id} [{claim.type.value}]"

            if claim.deterministic:
                if vc.result is VerificationResult.VERIFIED:
                    if vc.confidence is not ConfidenceLevel.PROVEN:
                        # Defensive: a verified deterministic fact must be PROVEN.
                        review.append(f"{label}: verified but not marked PROVEN")
                    else:
                        reasons.append(f"{label}: PROVEN - {vc.reason}")
                    continue
                if vc.result in _CONCLUSIVE_FAILURES:
                    entry = f"{label}: {vc.result.value} - {vc.reason}"
                    if claim.required:
                        blockers.append(entry)
                    else:
                        review.append(entry)
                continue

            # Evaluative claim: capped at INFERRED, so it is always open.
            if vc.open_evaluative:
                review.append(
                    f"{label}: evaluative claim at {vc.confidence.value} - needs human review"
                )

        if blockers:
            return GateDecision(
                result=GateResult.BLOCKED,
                reasons=reasons,
                blockers=blockers,
                review_items=review,
            )
        if review:
            return GateDecision(
                result=GateResult.REVIEW_REQUIRED,
                reasons=reasons,
                blockers=[],
                review_items=review,
            )
        return GateDecision(
            result=GateResult.PASS,
            reasons=reasons or ["no claims to check"],
            blockers=[],
            review_items=[],
        )


def has_deterministic_blockers(verified: list[VerifiedClaim]) -> bool:
    """True when a required deterministic fact already failed.

    The orchestrator uses this to stop before any expensive reasoning step.
    """
    return any(
        vc.claim.deterministic
        and vc.claim.required
        and vc.result in _CONCLUSIVE_FAILURES
        for vc in verified
    )
