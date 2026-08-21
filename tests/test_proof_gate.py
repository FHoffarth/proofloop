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


def _eval_claim(claim_type: ClaimType = ClaimType.BUG_FIXED) -> VerifiedClaim:
    return VerifiedClaim(
        claim=Claim(
            id=claim_type.value.lower().replace("_", "-"),
            type=claim_type,
            statement="a judgement call",
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


EVALUATIVE_TYPES = [
    ClaimType.BUG_FIXED,
    ClaimType.SAFE_TO_MERGE,
    ClaimType.NO_REGRESSION,
    ClaimType.ARCHITECTURE_CORRECT,
    ClaimType.GENERAL_INFERENCE,
]


@pytest.mark.parametrize("claim_type", EVALUATIVE_TYPES)
def test_gate_rejects_a_forged_proven_evaluative_claim(claim_type: ClaimType) -> None:
    """An evaluative claim stamped PROVEN upstream must still go to review.

    The gate decides this from the claim type alone. It must not trust the
    confidence it is handed, and it must not rely on the verifier having
    capped it: forged state cannot override deterministic gate policy.
    """
    forged = _eval_claim(claim_type)
    forged.confidence = ConfidenceLevel.PROVEN
    forged.result = VerificationResult.VERIFIED

    decision = ProofGate().evaluate([forged])

    assert decision.result is GateResult.REVIEW_REQUIRED
    # It appears explicitly, and it is named as a rejected forgery.
    assert len(decision.review_items) == 1
    assert forged.claim.id in decision.review_items[0]
    assert "stamped PROVEN" in decision.review_items[0]
    # It never contributes a PROVEN reason.
    assert decision.reasons == []
    assert not any("PROVEN" in reason for reason in decision.reasons)


@pytest.mark.parametrize("claim_type", EVALUATIVE_TYPES)
def test_forged_proven_evaluative_claim_cannot_produce_pass(
    claim_type: ClaimType,
) -> None:
    """Even alongside a genuinely proven deterministic fact."""
    forged = _eval_claim(claim_type)
    forged.confidence = ConfidenceLevel.PROVEN
    decision = ProofGate().evaluate([_det(VerificationResult.VERIFIED), forged])
    assert decision.result is GateResult.REVIEW_REQUIRED


@pytest.mark.parametrize("claim_type", EVALUATIVE_TYPES)
def test_deterministic_blockers_still_outrank_a_forged_proven_claim(
    claim_type: ClaimType,
) -> None:
    forged = _eval_claim(claim_type)
    forged.confidence = ConfidenceLevel.PROVEN
    decision = ProofGate().evaluate([_det(VerificationResult.FAILED), forged])
    assert decision.result is GateResult.BLOCKED
    assert decision.blockers


@pytest.mark.parametrize("claim_type", EVALUATIVE_TYPES)
def test_forged_proven_claim_is_still_open(claim_type: ClaimType) -> None:
    """The schema-level view agrees with the gate: it is not closed."""
    forged = _eval_claim(claim_type)
    forged.confidence = ConfidenceLevel.PROVEN
    assert forged.open_evaluative is True


@pytest.mark.parametrize("claim_type", EVALUATIVE_TYPES)
def test_required_forged_proven_claim_does_not_block_or_pass(
    claim_type: ClaimType,
) -> None:
    """``required`` on an evaluative claim does not turn it into a blocker."""
    forged = _eval_claim(claim_type)
    forged.claim.required = True
    forged.confidence = ConfidenceLevel.PROVEN
    decision = ProofGate().evaluate([forged])
    assert decision.result is GateResult.REVIEW_REQUIRED


def test_has_deterministic_blockers() -> None:
    assert has_deterministic_blockers([_det(VerificationResult.FAILED)]) is True
    assert has_deterministic_blockers([_det(VerificationResult.VERIFIED)]) is False
    assert has_deterministic_blockers([_eval_claim()]) is False
