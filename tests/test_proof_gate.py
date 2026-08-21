"""The gate is the authority. These tests pin its rules."""

from __future__ import annotations

import pytest

from proofloop.gate import ProofGate, has_deterministic_blockers
from proofloop.schemas import (
    Claim,
    ClaimType,
    ConfidenceLevel,
    Evidence,
    GateResult,
    VerificationResult,
    VerifiedClaim,
)


def _det(result: VerificationResult, required: bool = True) -> VerifiedClaim:
    confidence = (
        ConfidenceLevel.PROVEN
        if result is VerificationResult.VERIFIED
        else ConfidenceLevel.UNVERIFIED
    )
    return VerifiedClaim(
        claim=Claim(
            id=f"det-{result.value.lower()}",
            type=ClaimType.COMMIT_EXISTS,
            statement="commit exists",
            required=required,
            params={"commit": "HEAD"},
        ),
        result=result,
        confidence=confidence,
        evidence=[Evidence(kind="commit_exists", ok=result is VerificationResult.VERIFIED)],
        reason=result.value,
    )


def _eval_claim() -> VerifiedClaim:
    return VerifiedClaim(
        claim=Claim(
            id="bug-fixed",
            type=ClaimType.BUG_FIXED,
            statement="the bug is fixed",
            required=False,
        ),
        result=VerificationResult.INSUFFICIENT,
        confidence=ConfidenceLevel.INFERRED,
        reason="evaluative",
    )


def test_pass_requires_verified_facts_and_no_open_evaluative_claims() -> None:
    decision = ProofGate().evaluate([_det(VerificationResult.VERIFIED)])
    assert decision.result is GateResult.PASS


def test_empty_claim_set_passes_but_says_so() -> None:
    decision = ProofGate().evaluate([])
    assert decision.result is GateResult.PASS
    assert decision.reasons == ["no claims to check"]


@pytest.mark.parametrize(
    "result",
    [
        VerificationResult.FAILED,
        VerificationResult.INSUFFICIENT,
        VerificationResult.NOT_CHECKED,
    ],
)
def test_required_fact_that_is_not_verified_blocks(result: VerificationResult) -> None:
    decision = ProofGate().evaluate([_det(result)])
    assert decision.result is GateResult.BLOCKED
    assert decision.blockers


def test_missing_evidence_fails_closed() -> None:
    """NOT_CHECKED is missing evidence, and missing evidence must block."""
    decision = ProofGate().evaluate([_det(VerificationResult.NOT_CHECKED)])
    assert decision.result is GateResult.BLOCKED


def test_optional_failed_fact_only_needs_review() -> None:
    decision = ProofGate().evaluate([_det(VerificationResult.FAILED, required=False)])
    assert decision.result is GateResult.REVIEW_REQUIRED


def test_open_evaluative_claim_forces_review() -> None:
    decision = ProofGate().evaluate([_det(VerificationResult.VERIFIED), _eval_claim()])
    assert decision.result is GateResult.REVIEW_REQUIRED
    assert any("evaluative" in item for item in decision.review_items)


def test_blocked_beats_review() -> None:
    decision = ProofGate().evaluate([_det(VerificationResult.FAILED), _eval_claim()])
    assert decision.result is GateResult.BLOCKED


def test_pipeline_errors_are_blockers() -> None:
    decision = ProofGate().evaluate(
        [_det(VerificationResult.VERIFIED)], errors=["provider exploded"]
    )
    assert decision.result is GateResult.BLOCKED
    assert "provider exploded" in decision.blockers


def test_gate_ignores_a_forged_proven_confidence_on_an_evaluative_claim() -> None:
    """Even if something upstream stamps PROVEN on a judgement call.

    The gate's own accounting must not turn that into a PASS silently; a
    deterministic fact is still required for anything to be proven.
    """
    forged = _eval_claim()
    forged.confidence = ConfidenceLevel.PROVEN
    decision = ProofGate().evaluate([forged])
    # The gate does not treat evaluative claims as facts, so nothing is proven.
    assert decision.result is not GateResult.BLOCKED
    assert not any("PROVEN" in reason for reason in decision.reasons)


def test_has_deterministic_blockers() -> None:
    assert has_deterministic_blockers([_det(VerificationResult.FAILED)]) is True
    assert has_deterministic_blockers([_det(VerificationResult.VERIFIED)]) is False
    assert has_deterministic_blockers([_eval_claim()]) is False
