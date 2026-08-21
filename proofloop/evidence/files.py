"""File evidence, with every path confined to the repository root."""

from __future__ import annotations

from pathlib import Path

from ..schemas import Evidence
from . import UnsafePath


def resolve_repo_root(repo: Path | str) -> Path:
    root = Path(repo).expanduser().resolve()
    if not root.is_dir():
        raise UnsafePath(f"repo root is not a directory: {root}")
    return root


def resolve_in_repo(repo_root: Path, relative: str) -> Path:
    """Resolve ``relative`` against ``repo_root`` and refuse to leave it.

    Absolute paths, ``..`` traversal and symlinks that point outside the root
    are all rejected. Resolution happens *before* the containment check, so a
    symlink cannot smuggle the target out of the tree.
    """
    if not isinstance(relative, str) or not relative:
        raise UnsafePath("empty path")
    if "\x00" in relative:
        raise UnsafePath("path contains a NUL byte")

    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive or relative.startswith(("/", "\\")):
        raise UnsafePath(f"absolute paths are not allowed: {relative!r}")

    root = repo_root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        raise UnsafePath(f"path escapes repo root: {relative!r}")
    return resolved


def file_contains(repo_root: Path, relative: str, needle: str) -> Evidence:
    """Evidence that ``relative`` exists and contains ``needle``.

    A missing file is failing evidence, never absent evidence: missing
    evidence fails closed.
    """
    try:
        target = resolve_in_repo(repo_root, relative)
    except UnsafePath as exc:
        return Evidence(
            kind="file_contains",
            ok=False,
            detail=f"unsafe path rejected: {exc}",
        )

    if not target.is_file():
        return Evidence(
            kind="file_contains",
            ok=False,
            detail=f"file not found: {relative}",
        )

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return Evidence(kind="file_contains", ok=False, detail=f"unreadable: {exc}")

    found = needle in text
    return Evidence(
        kind="file_contains",
        ok=found,
        detail=(
            f"{relative} contains {needle!r}"
            if found
            else f"{relative} does not contain {needle!r}"
        ),
        output=f"{len(text)} chars scanned",
    )
