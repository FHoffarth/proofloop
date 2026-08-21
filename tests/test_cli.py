"""CLI contract: exit codes, and a dry run that needs neither keys nor network."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path

import pytest

from proofloop.cli import EXIT_BLOCKED, EXIT_PASS, EXIT_REVIEW, main

BOGUS_COMMIT = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

API_KEY_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
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
    (root / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add hello")
    return root


def test_exit_0_on_pass(repo: Path) -> None:
    code = main(["solve", "clean tree?", "--repo", str(repo), "--profile", "quick-check"])
    assert code == EXIT_PASS == 0


def test_exit_1_on_review_required(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    code = main(
        [
            "solve",
            "did this fix the bug?",
            "--repo",
            str(repo),
            "--profile",
            "verify-fix",
            "--commit",
            head,
            "--node-id",
            "test_ok.py",
        ]
    )
    assert code == EXIT_REVIEW == 1


def test_exit_2_on_blocked(repo: Path) -> None:
    code = main(
        [
            "solve",
            "verify a commit that does not exist",
            "--repo",
            str(repo),
            "--profile",
            "verify-commit",
            "--commit",
            BOGUS_COMMIT,
        ]
    )
    assert code == EXIT_BLOCKED == 2


def test_exit_2_on_pipeline_error(tmp_path: Path) -> None:
    code = main(["solve", "x", "--repo", str(tmp_path / "does-not-exist")])
    assert code == EXIT_BLOCKED


def test_inspect_file_profile(repo: Path) -> None:
    ok = main(
        [
            "solve",
            "does the file contain the marker?",
            "--repo",
            str(repo),
            "--profile",
            "inspect-file",
            "--path",
            "hello.txt",
            "--contains",
            "marker-alpha",
        ]
    )
    assert ok == EXIT_PASS

    blocked = main(
        [
            "solve",
            "does the file contain the marker?",
            "--repo",
            str(repo),
            "--profile",
            "inspect-file",
            "--path",
            "hello.txt",
            "--contains",
            "marker-omega",
        ]
    )
    assert blocked == EXIT_BLOCKED


def test_path_traversal_via_cli_is_blocked(repo: Path) -> None:
    code = main(
        [
            "solve",
            "read something outside the repo",
            "--repo",
            str(repo),
            "--profile",
            "inspect-file",
            "--path",
            "../../secrets.txt",
            "--contains",
            "token",
        ]
    )
    assert code == EXIT_BLOCKED


def test_json_output(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        ["solve", "clean?", "--repo", str(repo), "--profile", "quick-check", "--json"]
    )
    out = capsys.readouterr().out
    assert code == EXIT_PASS
    assert "final_gate" in out and "PASS" in out


def test_profiles_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["profiles"]) == EXIT_PASS
    out = capsys.readouterr().out
    for name in ("verify-commit", "verify-fix", "inspect-file", "quick-check", "none"):
        assert name in out


def test_dry_run_needs_no_api_keys_and_no_network(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in API_KEY_VARS:
        monkeypatch.delenv(var, raising=False)

    def _no_sockets(*args: object, **kwargs: object) -> None:
        raise AssertionError("ProofLoop opened a socket during a dry run")

    monkeypatch.setattr(socket, "socket", _no_sockets)
    monkeypatch.setattr(socket, "create_connection", _no_sockets)

    code = main(
        ["solve", "clean tree?", "--repo", str(repo), "--profile", "quick-check"]
    )
    assert code == EXIT_PASS
