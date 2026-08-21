"""Core vocabulary of ProofLoop.

An agent statement is a Claim. A Claim only becomes trustworthy when the
EvidenceVerifier attaches Evidence produced by a deterministic check.
Nothing in this module executes anything; it only describes shapes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """Every claim ProofLoop can carry.

    Deterministic types are mechanically checkable against git/files/tests.
    Evaluative types are judgement calls and can never be proven.
    """

    # deterministic
    COMMIT_EXISTS = "COMMIT_EXISTS"
    COMMIT_TOUCHES_FILES = "COMMIT_TOUCHES_FILES"
    FILE_CONTAINS = "FILE_CONTAINS"
    TEST_PASSED = "TEST_PASSED"
    WORKTREE_CLEAN = "WORKTREE_CLEAN"
    BRANCH_AT_SHA = "BRANCH_AT_SHA"

    # evaluative
    BUG_FIXED = "BUG_FIXED"
    SAFE_TO_MERGE = "SAFE_TO_MERGE"
    NO_REGRESSION = "NO_REGRESSION"
    ARCHITECTURE_CORRECT = "ARCHITECTURE_CORRECT"
    GENERAL_INFERENCE = "GENERAL_INFERENCE"


DETERMINISTIC_CLAIM_TYPES: frozenset[ClaimType] = frozenset(
    {
        ClaimType.COMMIT_EXISTS,
        ClaimType.COMMIT_TOUCHES_FILES,
        ClaimType.FILE_CONTAINS,
        ClaimType.TEST_PASSED,
        ClaimType.WORKTREE_CLEAN,
        ClaimType.BRANCH_AT_SHA,
    }
)

EVALUATIVE_CLAIM_TYPES: frozenset[ClaimType] = frozenset(
    {
        ClaimType.BUG_FIXED,
        ClaimType.SAFE_TO_MERGE,
        ClaimType.NO_REGRESSION,
        ClaimType.ARCHITECTURE_CORRECT,
        ClaimType.GENERAL_INFERENCE,
    }
)


def is_deterministic(claim_type: ClaimType) -> bool:
    return claim_type in DETERMINISTIC_CLAIM_TYPES


def is_evaluative(claim_type: ClaimType) -> bool:
    return claim_type in EVALUATIVE_CLAIM_TYPES


class VerificationResult(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    INSUFFICIENT = "INSUFFICIENT"
    NOT_CHECKED = "NOT_CHECKED"


class ConfidenceLevel(str, Enum):
    PROVEN = "PROVEN"
    INFERRED = "INFERRED"
    UNVERIFIED = "UNVERIFIED"


class GateResult(str, Enum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


class JudgeVerdictValue(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"


class Claim(BaseModel):
    """A statement awaiting evidence."""

    id: str
    type: ClaimType
    statement: str
    required: bool = True
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def deterministic(self) -> bool:
        return is_deterministic(self.type)

    @property
    def evaluative(self) -> bool:
        return is_evaluative(self.type)


class Evidence(BaseModel):
    """A single observation produced by a deterministic check.

    `ok=False` evidence is kept, never dropped: failed evidence must stay
    visible in the report.
    """

    kind: str
    command: list[str] = Field(default_factory=list)
    ok: bool
    detail: str = ""
    exit_code: int | None = None
    output: str = ""


class VerifiedClaim(BaseModel):
    """A claim plus the verdict the evidence supports."""

    claim: Claim
    result: VerificationResult = VerificationResult.NOT_CHECKED
    confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    evidence: list[Evidence] = Field(default_factory=list)
    reason: str = ""

    @property
    def open_evaluative(self) -> bool:
        """True when this is a judgement call that evidence cannot close."""
        return self.claim.evaluative and self.confidence is not ConfidenceLevel.PROVEN


class Plan(BaseModel):
    problem: str
    profile: str
    claims: list[Claim] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    plan: Plan
    notes: list[str] = Field(default_factory=list)
    added_claim_ids: list[str] = Field(default_factory=list)


class JudgeVerdict(BaseModel):
    verdict: JudgeVerdictValue
    rationale: str = ""
    skipped: bool = False
    skip_reason: str = ""


class GateDecision(BaseModel):
    result: GateResult
    reasons: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    review_items: list[str] = Field(default_factory=list)


class RunReport(BaseModel):
    problem: str
    profile: str
    repo: str
    plan: Plan
    critique_notes: list[str] = Field(default_factory=list)
    verified: list[VerifiedClaim] = Field(default_factory=list)
    pre_gate: GateDecision
    judge: JudgeVerdict | None = None
    final_gate: GateDecision
    provider: str = ""
    provider_calls: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        if self.final_gate.result is GateResult.PASS:
            return 0
        if self.final_gate.result is GateResult.REVIEW_REQUIRED:
            return 1
        return 2
