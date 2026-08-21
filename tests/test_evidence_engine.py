"""Adversarial tests for the evidence layer."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from proofloop.evidence import (
    UnsafeCommand,
    UnsafePath,
    safe_run,
    validate_marker,
    validate_ref,
    validate_sha,
)
from proofloop.evidence.files import file_contains, resolve_in_repo
from proofloop.evidence.git import (
    branch_at_sha,
    commit_exists,
    commit_touches_files,
    worktree_clean,
)
from proofloop.evidence.tests import validate_node_id, verify_tests_passed
from proofloop.evidence.verifier import EvidenceVerifier
from proofloop.schemas import (
    Claim,
    ClaimType,
    ConfidenceLevel,
    VerificationResult,
)


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
    _git(root, "add", "hello.txt")
    _git(root, "commit", "-m", "add hello")
    return root


# --- path safety ---------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "../outside.txt",
        "../../etc/passwd",
        "sub/../../outside.txt",
        "/etc/passwd",
        r"\windows\system32",
    ],
)
def test_path_traversal_blocked(repo: Path, bad: str) -> None:
    with pytest.raises(UnsafePath):
        resolve_in_repo(repo, bad)


def test_path_traversal_is_failing_evidence_not_an_exception(repo: Path) -> None:
    ev = file_contains(repo, "../outside.txt", "anything")
    assert ev.ok is False
    assert "unsafe path" in ev.detail


def test_paths_inside_repo_resolve(repo: Path) -> None:
    assert resolve_in_repo(repo, "hello.txt") == (repo / "hello.txt").resolve()


# --- command safety ------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "abc123; rm -rf /",
        "main && curl evil.example",
        "$(whoami)",
        "`id`",
        "--upload-pack=touch pwned",
        "main | cat /etc/passwd",
        "",
    ],
)
def test_command_injection_blocked_in_refs(bad: str) -> None:
    with pytest.raises(UnsafeCommand):
        validate_ref(bad)


def test_injection_in_commit_claim_is_blocked_evidence(repo: Path) -> None:
    ev = commit_exists(repo, "HEAD; rm -rf /")
    assert ev.ok is False
    assert ev.detail.startswith("blocked:")
    assert ev.command == []  # nothing was ever spawned


def test_option_injection_into_pytest_blocked() -> None:
    with pytest.raises(UnsafeCommand):
        validate_node_id("-p no:cacheprovider")


def test_safe_run_rejects_non_allowlisted_executable(repo: Path) -> None:
    with pytest.raises(UnsafeCommand):
        safe_run(["curl", "https://example.invalid"], cwd=repo)


def test_safe_run_rejects_non_allowlisted_git_subcommand(repo: Path) -> None:
    with pytest.raises(UnsafeCommand):
        safe_run(["git", "push", "origin", "main"], cwd=repo)


def test_safe_run_allows_allowlisted_git_subcommand(repo: Path) -> None:
    proc = safe_run(["git", "rev-parse", "HEAD"], cwd=repo)
    assert proc.returncode == 0


PYTEST_HEAD = [sys.executable, "-m", "pytest", "-q"]
TRIVIAL_TEST = "def test_ok():\n    assert True\n"


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["-m", "not integration"],
        ["-m", "integration"],
        ["--", "tests/test_x.py"],
        ["-m", "not integration", "--", "tests/test_x.py::test_case"],
        ["-m", "not integration", "--", "tests/test_x.py::test_case[param-1]"],
    ],
)
def test_pytest_argv_grammar_allows_only_the_shapes_proofloop_builds(
    repo: Path, extra: list[str]
) -> None:
    from proofloop.evidence import _check_pytest_argv

    _check_pytest_argv(PYTEST_HEAD + extra)  # must not raise


@pytest.mark.parametrize(
    "extra",
    [
        ["-p", "no:cacheprovider"],
        ["-p", "evil_plugin"],
        ["--basetemp=/tmp/pwned"],
        ["--rootdir=/"],
        ["-c", "evil.ini"],
        ["--pdb"],
        ["--co"],
        ["tests/"],                      # bare path without the -- separator
        ["--", "tests/a.py", "tests/b.py"],  # more than one target
        ["--"],                          # separator with no target
        ["-m"],                          # marker flag with no expression
        ["-m", "not integration or evil"],
        ["-m", "--basetemp=/tmp"],
        ["--", "-p"],
        ["--", "../../outside.py"],
        ["-q"],                          # trailing junk
        ["-m", "not integration", "-p", "x"],
    ],
)
def test_pytest_argv_grammar_rejects_everything_else(extra: list[str]) -> None:
    with pytest.raises(UnsafeCommand):
        safe_run(PYTEST_HEAD + extra, cwd=Path.cwd())


@pytest.mark.parametrize(
    "argv",
    [
        [sys.executable, "-m", "pytest"],          # missing -q
        [sys.executable, "-m", "pytest", "-v"],    # wrong verbosity flag
        [sys.executable, "-c", "import os"],       # not pytest at all
        [sys.executable, "-m", "pip", "install", "openai"],
        [sys.executable],
    ],
)
def test_pytest_argv_head_must_match_exactly(argv: list[str]) -> None:
    with pytest.raises(UnsafeCommand):
        safe_run(argv, cwd=Path.cwd())


def test_validate_marker_rejects_expressions() -> None:
    assert validate_marker("not integration") == "not integration"
    for bad in ["not integration or slow", "-m", "", "not (integration)", "a;b"]:
        with pytest.raises(UnsafeCommand):
            validate_marker(bad)


def test_verify_tests_passed_builds_an_allow_listed_argv(tmp_path: Path) -> None:
    """The argv the real checker builds must satisfy the grammar."""
    from proofloop.evidence import _check_pytest_argv

    root = tmp_path / "proj"
    root.mkdir()
    (root / "test_ok.py").write_text(TRIVIAL_TEST, encoding="utf-8")
    ev = verify_tests_passed(root, node_id="test_ok.py", timeout=120)
    _check_pytest_argv(ev.command)


def test_validate_sha_rejects_garbage() -> None:
    with pytest.raises(UnsafeCommand):
        validate_sha("not-a-sha")


# --- git evidence --------------------------------------------------------


def test_invalid_commit_is_failed_evidence(repo: Path) -> None:
    ev = commit_exists(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    assert ev.ok is False


def test_valid_commit_verifies(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    assert commit_exists(repo, head).ok is True


def test_commit_touches_files(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    assert commit_touches_files(repo, head, ["hello.txt"]).ok is True
    ev = commit_touches_files(repo, head, ["never.txt"])
    assert ev.ok is False
    assert "never.txt" in ev.detail


def test_worktree_clean_verified(repo: Path) -> None:
    assert worktree_clean(repo).ok is True
    (repo / "hello.txt").write_text("changed\n", encoding="utf-8")
    dirty = worktree_clean(repo)
    assert dirty.ok is False
    assert "dirty" in dirty.detail


def test_branch_at_sha(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    assert branch_at_sha(repo, "main", head).ok is True
    assert branch_at_sha(repo, "main", "0" * 40).ok is False


# --- file evidence -------------------------------------------------------


def test_file_contains_verified(repo: Path) -> None:
    assert file_contains(repo, "hello.txt", "marker-alpha").ok is True
    assert file_contains(repo, "hello.txt", "marker-omega").ok is False


def test_missing_file_fails_closed(repo: Path) -> None:
    ev = file_contains(repo, "nope.txt", "x")
    assert ev.ok is False
    assert "not found" in ev.detail


# --- test evidence -------------------------------------------------------


def test_verify_tests_passed_runs_pytest(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    ev = verify_tests_passed(root, node_id="test_ok.py", timeout=120)
    assert ev.command[:3] == [sys.executable, "-m", "pytest"]
    assert ev.ok is True


def test_verify_tests_passed_reports_failure(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    ev = verify_tests_passed(root, node_id="test_bad.py", timeout=120)
    assert ev.ok is False
    assert ev.exit_code not in (0, None)


# --- verifier ------------------------------------------------------------


def test_deterministic_claim_becomes_proven(repo: Path) -> None:
    verifier = EvidenceVerifier(repo)
    vc = verifier.verify(
        Claim(
            id="c1",
            type=ClaimType.WORKTREE_CLEAN,
            statement="tree is clean",
            params={},
        )
    )
    assert vc.result is VerificationResult.VERIFIED
    assert vc.confidence is ConfidenceLevel.PROVEN


@pytest.mark.parametrize(
    "claim_type",
    [
        ClaimType.BUG_FIXED,
        ClaimType.SAFE_TO_MERGE,
        ClaimType.NO_REGRESSION,
        ClaimType.ARCHITECTURE_CORRECT,
        ClaimType.GENERAL_INFERENCE,
    ],
)
def test_evaluative_claims_never_proven(repo: Path, claim_type: ClaimType) -> None:
    verifier = EvidenceVerifier(repo)
    vc = verifier.verify(
        Claim(id="e1", type=claim_type, statement="a judgement call", params={})
    )
    assert vc.confidence is not ConfidenceLevel.PROVEN
    assert vc.confidence is ConfidenceLevel.INFERRED
    assert vc.result is VerificationResult.INSUFFICIENT


def test_failed_evidence_stays_visible(repo: Path) -> None:
    verifier = EvidenceVerifier(repo)
    vc = verifier.verify(
        Claim(
            id="c2",
            type=ClaimType.FILE_CONTAINS,
            statement="missing file",
            params={"path": "nope.txt", "text": "x"},
        )
    )
    assert vc.evidence, "failing evidence must be kept, not dropped"
    assert vc.evidence[0].ok is False


def test_verifier_rejects_repo_that_is_not_a_directory(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(UnsafePath):
        EvidenceVerifier(target)
