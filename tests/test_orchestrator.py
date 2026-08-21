"""End-to-end pipeline behaviour, still fully offline."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from proofloop.orchestrator import Orchestrator
from proofloop.providers import FakeProvider
from proofloop.schemas import (
    ClaimType,
    ConfidenceLevel,
    GateResult,
    JudgeVerdictValue,
    VerificationResult,
)

BOGUS_COMMIT = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "ProofLoop Test")
    (root / "hello.txt").write_text("marker-alpha\n", encoding="utf-8")
    (root / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add hello")
    return root


def test_clean_repo_passes(repo: Path) -> None:
    report = Orchestrator(repo=repo, provider=FakeProvider()).run(
        "is the tree clean?", "quick-check", {}
    )
    assert report.final_gate.result is GateResult.PASS
    assert report.exit_code == 0


def test_invalid_commit_blocks_and_judge_is_skipped(repo: Path) -> None:
    provider = FakeProvider(responses={"judge": "ACCEPT everything looks great"})
    report = Orchestrator(repo=repo, provider=provider).run(
        "verify a commit that does not exist",
        "verify-commit",
        {"commit": BOGUS_COMMIT},
    )

    assert report.pre_gate.result is GateResult.BLOCKED
    assert report.final_gate.result is GateResult.BLOCKED
    assert report.exit_code == 2

    assert report.judge is not None
    assert report.judge.skipped is True
    assert "pre-gate BLOCKED" in report.judge.skip_reason
    # Deterministic blockers stop expensive reasoning early: planner + critic
    # were called, the judge was not.
    assert [role for role, _ in provider.prompts] == ["planner", "critic"]


def test_gate_veto_survives_a_judge_that_says_accept(repo: Path) -> None:
    """The judge may ACCEPT. Open evaluative claims still force review."""
    provider = FakeProvider(responses={"judge": "ACCEPT - I am fully convinced."})
    head = _git(repo, "rev-parse", "HEAD")

    report = Orchestrator(repo=repo, provider=provider).run(
        "verify the fix",
        "verify-fix",
        {"commit": head, "node_id": "test_ok.py"},
    )

    assert report.judge is not None
    assert report.judge.skipped is False
    assert report.judge.verdict is JudgeVerdictValue.ACCEPT
    # ... and the gate is unmoved.
    assert report.final_gate.result is GateResult.REVIEW_REQUIRED
    assert report.exit_code == 1

    by_id = {vc.claim.id: vc for vc in report.verified}
    assert by_id["commit-exists"].confidence is ConfidenceLevel.PROVEN
    assert by_id["tests-pass"].result is VerificationResult.VERIFIED
    assert by_id["bug-fixed"].confidence is ConfidenceLevel.INFERRED


def test_evaluative_bug_fixed_is_never_proven_end_to_end(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    report = Orchestrator(repo=repo, provider=FakeProvider()).run(
        "did it fix the bug?", "verify-fix", {"commit": head, "node_id": "test_ok.py"}
    )
    evaluative = [vc for vc in report.verified if vc.claim.type is ClaimType.BUG_FIXED]
    assert evaluative
    assert all(vc.confidence is not ConfidenceLevel.PROVEN for vc in evaluative)


def test_provider_timeout_aborts_cleanly(repo: Path) -> None:
    provider = FakeProvider(simulate_timeout=True)
    report = Orchestrator(repo=repo, provider=provider).run(
        "anything", "quick-check", {}
    )
    assert report.final_gate.result is GateResult.BLOCKED
    assert report.exit_code == 2
    assert any("provider failed" in err for err in report.errors)


def test_provider_timeout_in_judge_only_fails_closed(repo: Path) -> None:
    provider = FakeProvider(simulate_timeout=True, fail_on_role="judge")
    report = Orchestrator(repo=repo, provider=provider).run(
        "anything", "quick-check", {}
    )
    assert report.judge is not None
    assert report.judge.skipped is True
    assert report.final_gate.result is GateResult.BLOCKED


def test_no_judge_flag_skips_the_judge(repo: Path) -> None:
    provider = FakeProvider()
    report = Orchestrator(repo=repo, provider=provider, use_judge=False).run(
        "anything", "quick-check", {}
    )
    assert report.judge is not None and report.judge.skipped is True
    assert "judge" not in [role for role, _ in provider.prompts]
    assert report.final_gate.result is GateResult.PASS


def test_unknown_profile_is_a_blocked_run(repo: Path) -> None:
    report = Orchestrator(repo=repo, provider=FakeProvider()).run(
        "anything", "no-such-profile", {}
    )
    assert report.final_gate.result is GateResult.BLOCKED
    assert any("profile error" in err for err in report.errors)


def test_missing_required_profile_input_is_a_blocked_run(repo: Path) -> None:
    report = Orchestrator(repo=repo, provider=FakeProvider()).run(
        "verify a commit", "verify-commit", {}
    )
    assert report.final_gate.result is GateResult.BLOCKED
    assert any("requires: commit" in err for err in report.errors)


def test_dirty_worktree_blocks(repo: Path) -> None:
    (repo / "hello.txt").write_text("dirty\n", encoding="utf-8")
    report = Orchestrator(repo=repo, provider=FakeProvider()).run(
        "is the tree clean?", "quick-check", {}
    )
    assert report.final_gate.result is GateResult.BLOCKED
    assert report.final_gate.blockers


def test_profile_none_has_nothing_to_prove(repo: Path) -> None:
    report = Orchestrator(repo=repo, provider=FakeProvider()).run(
        "just think about it", "none", {}
    )
    assert report.verified == []
    assert report.final_gate.result is GateResult.PASS
    assert any("no claims" in note for note in report.critique_notes)
