"""Git evidence. Read-only commands only, all argv, all allow-listed."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..schemas import Evidence
from . import UnsafeCommand, UnsafePath, safe_run, validate_ref, validate_sha
from .files import resolve_in_repo


def _run(argv: list[str], cwd: Path, kind: str, timeout: int = 30) -> Evidence:
    try:
        proc = safe_run(argv, cwd=cwd, timeout=timeout)
    except UnsafeCommand as exc:
        return Evidence(kind=kind, command=argv, ok=False, detail=f"blocked: {exc}")
    except subprocess.TimeoutExpired:
        return Evidence(kind=kind, command=argv, ok=False, detail="git command timed out")
    except OSError as exc:
        return Evidence(kind=kind, command=argv, ok=False, detail=f"git unavailable: {exc}")
    return Evidence(
        kind=kind,
        command=argv,
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        detail=(proc.stderr or "").strip()[:2000],
        output=(proc.stdout or "").strip()[:8000],
    )


def is_git_repo(repo_root: Path) -> Evidence:
    return _run(["git", "rev-parse", "--is-inside-work-tree"], repo_root, "is_git_repo")


def commit_exists(repo_root: Path, commit: str) -> Evidence:
    try:
        ref = validate_ref(commit)
    except UnsafeCommand as exc:
        return Evidence(kind="commit_exists", ok=False, detail=f"blocked: {exc}")
    ev = _run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
        repo_root,
        "commit_exists",
    )
    if ev.ok:
        ev.detail = f"commit {ref} exists"
    elif not ev.detail:
        ev.detail = f"commit {ref} not found"
    return ev


def resolve_commit(repo_root: Path, commit: str) -> Evidence:
    try:
        ref = validate_ref(commit)
    except UnsafeCommand as exc:
        return Evidence(kind="resolve_commit", ok=False, detail=f"blocked: {exc}")
    return _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], repo_root, "resolve_commit")


def commit_touches_files(repo_root: Path, commit: str, files: list[str]) -> Evidence:
    """Evidence that ``commit`` changed every path in ``files``."""
    if not files:
        return Evidence(
            kind="commit_touches_files",
            ok=False,
            detail="no files given to check",
        )
    try:
        ref = validate_ref(commit)
        wanted = []
        for rel in files:
            resolve_in_repo(repo_root, rel)  # containment check only
            wanted.append(rel.replace("\\", "/").lstrip("./"))
    except (UnsafeCommand, UnsafePath) as exc:
        return Evidence(kind="commit_touches_files", ok=False, detail=f"blocked: {exc}")

    ev = _run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", ref],
        repo_root,
        "commit_touches_files",
    )
    if not ev.ok:
        return ev

    touched = {line.strip() for line in ev.output.splitlines() if line.strip()}
    missing = [rel for rel in wanted if rel not in touched]
    ev.ok = not missing
    ev.detail = (
        f"{ref} touches all of {wanted}"
        if ev.ok
        else f"{ref} does not touch: {missing}"
    )
    return ev


def worktree_clean(repo_root: Path) -> Evidence:
    ev = _run(["git", "status", "--porcelain"], repo_root, "worktree_clean")
    if not ev.ok:
        return ev
    dirty = [line for line in ev.output.splitlines() if line.strip()]
    ev.ok = not dirty
    ev.detail = "working tree clean" if ev.ok else f"{len(dirty)} dirty path(s)"
    return ev


def branch_at_sha(repo_root: Path, branch: str, sha: str) -> Evidence:
    try:
        ref = validate_ref(branch)
        want = validate_sha(sha)
    except UnsafeCommand as exc:
        return Evidence(kind="branch_at_sha", ok=False, detail=f"blocked: {exc}")

    ev = _run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], repo_root, "branch_at_sha")
    if not ev.ok:
        ev.detail = ev.detail or f"branch {ref} not found"
        return ev

    head = ev.output.strip()
    ev.ok = head.lower().startswith(want.lower())
    ev.detail = (
        f"{ref} is at {head}" if ev.ok else f"{ref} is at {head}, expected {want}"
    )
    return ev
