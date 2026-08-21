"""Judge: an advisory verdict over already-collected evidence.

The judge runs after the pre-gate and its verdict is recorded in the report.
It is never consulted by the gate. See :mod:`proofloop.gate`.
"""

from __future__ import annotations

from ..providers import Provider
from ..schemas import JudgeVerdict, JudgeVerdictValue, VerifiedClaim

PROMPT = (
    "You are a judge in an evidence-first pipeline.\n"
    "Verified claims:\n{claims}\n"
    "Answer with exactly one of ACCEPT, REJECT or ABSTAIN, then a short rationale.\n"
    "Your verdict is advisory: it cannot change the proof gate."
)


def _parse_verdict(text: str) -> JudgeVerdictValue:
    upper = (text or "").upper()
    for value in (
        JudgeVerdictValue.REJECT,
        JudgeVerdictValue.ACCEPT,
        JudgeVerdictValue.ABSTAIN,
    ):
        if value.value in upper:
            return value
    return JudgeVerdictValue.ABSTAIN


class Judge:
    role = "judge"

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def judge(self, verified: list[VerifiedClaim]) -> JudgeVerdict:
        rendered = "\n".join(
            f"- {vc.claim.id} [{vc.claim.type.value}] {vc.result.value}/"
            f"{vc.confidence.value}: {vc.reason}"
            for vc in verified
        ) or "- (no verified claims)"

        response = self.provider.generate(PROMPT.format(claims=rendered), role=self.role)
        return JudgeVerdict(
            verdict=_parse_verdict(response.text),
            rationale=response.text.strip(),
        )

    @staticmethod
    def skipped(reason: str) -> JudgeVerdict:
        return JudgeVerdict(
            verdict=JudgeVerdictValue.ABSTAIN,
            rationale="",
            skipped=True,
            skip_reason=reason,
        )
