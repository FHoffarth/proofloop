"""The EvidenceVerifier: turns Claims into VerifiedClaims.

This is the only place allowed to hand out ``PROVEN``, and it hands it out
only for deterministic claim types backed by passing evidence.
"""

from __future__ import annotations

from pathlib import Path

from ..schemas import (
    Claim,
    ClaimType,
    ConfidenceLevel,
    Evidence,
    VerificationResult,
    VerifiedClaim,
    is_deterministic,
)
from . import UnsafePath
from .files import file_contains, resolve_repo_root
from .git import branch_at_sha, commit_exists, commit_touches_files, worktree_clean
from .tests import verify_tests_passed

#: Evidence detail prefixes that mean "the check could not be performed"
#: rather than "the check performed and failed".
_INSUFFICIENT_MARKERS = ("blocked:", "git unavailable", "cannot run pytest", "no files given")


def cap_confidence(claim: Claim, confidence: ConfidenceLevel) -> ConfidenceLevel:
    """Enforce the central invariant: evaluative claims never reach PROVEN."""
    if confidence is ConfidenceLevel.PROVEN and not is_deterministic(claim.type):
        return ConfidenceLevel.INFERRED
    return confidence


class EvidenceVerifier:
    def __init__(self, repo: Path | str, test_timeout: int = 300) -> None:
        self.repo_root = resolve_repo_root(repo)
        self.test_timeout = test_timeout

    def verify_all(self, claims: list[Claim]) -> list[VerifiedClaim]:
        return [self.verify(claim) for claim in claims]

    def verify(self, claim: Claim) -> VerifiedClaim:
        if not is_deterministic(claim.type):
            # Evaluative claims are judgement calls. No evidence can prove
            # them, so they stay open for the gate to route to review.
            return VerifiedClaim(
                claim=claim,
                result=VerificationResult.INSUFFICIENT,
                confidence=cap_confidence(claim, ConfidenceLevel.INFERRED),
                evidence=[],
                reason="evaluative claim: not mechanically verifiable",
            )

        try:
            evidence = self._collect(claim)
        except UnsafePath as exc:
            evidence = Evidence(kind=claim.type.value.lower(), ok=False, detail=f"blocked: {exc}")

        return self._grade(claim, evidence)

    def _collect(self, claim: Claim) -> Evidence:
        p = claim.params
        if claim.type is ClaimType.COMMIT_EXISTS:
            return commit_exists(self.repo_root, str(p.get("commit", "")))
        if claim.type is ClaimType.COMMIT_TOUCHES_FILES:
            files = p.get("files") or []
            return commit_touches_files(self.repo_root, str(p.get("commit", "")), list(files))
        if claim.type is ClaimType.FILE_CONTAINS:
            return file_contains(self.repo_root, str(p.get("path", "")), str(p.get("text", "")))
        if claim.type is ClaimType.TEST_PASSED:
            return verify_tests_passed(
                self.repo_root,
                node_id=p.get("node_id"),
                timeout=self.test_timeout,
            )
        if claim.type is ClaimType.WORKTREE_CLEAN:
            return worktree_clean(self.repo_root)
        if claim.type is ClaimType.BRANCH_AT_SHA:
            return branch_at_sha(self.repo_root, str(p.get("branch", "")), str(p.get("sha", "")))
        # Unknown deterministic type: fail closed rather than silently pass.
        return Evidence(
            kind="unsupported",
            ok=False,
            detail=f"no checker for claim type {claim.type.value}",
        )

    @staticmethod
    def _grade(claim: Claim, evidence: Evidence) -> VerifiedClaim:
        if evidence.ok:
            return VerifiedClaim(
                claim=claim,
                result=VerificationResult.VERIFIED,
                confidence=cap_confidence(claim, ConfidenceLevel.PROVEN),
                evidence=[evidence],
                reason=evidence.detail or "check passed",
            )

        detail = (evidence.detail or "").lower()
        could_not_run = any(marker in detail for marker in _INSUFFICIENT_MARKERS)
        result = (
            VerificationResult.INSUFFICIENT if could_not_run else VerificationResult.FAILED
        )
        return VerifiedClaim(
            claim=claim,
            result=result,
            confidence=ConfidenceLevel.UNVERIFIED,
            evidence=[evidence],  # failing evidence is kept, never dropped
            reason=evidence.detail or "check did not pass",
        )
