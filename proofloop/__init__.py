"""ProofLoop: agent reports are claims, git/tests/artifacts are evidence."""

from .gate import ProofGate
from .orchestrator import Orchestrator
from .schemas import (
    Claim,
    ClaimType,
    ConfidenceLevel,
    Evidence,
    GateDecision,
    GateResult,
    RunReport,
    VerificationResult,
    VerifiedClaim,
)

__version__ = "0.1.0"

__all__ = [
    "Claim",
    "ClaimType",
    "ConfidenceLevel",
    "Evidence",
    "GateDecision",
    "GateResult",
    "Orchestrator",
    "ProofGate",
    "RunReport",
    "VerificationResult",
    "VerifiedClaim",
    "__version__",
]
