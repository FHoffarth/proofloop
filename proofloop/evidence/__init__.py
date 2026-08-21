"""Deterministic evidence collection.

Everything in this package obeys the same three rules:

* no ``shell=True`` -- commands are argv lists, never strings;
* only explicitly allow-listed executables and subcommands may run;
* every caller-supplied token is pattern-validated before it reaches argv,
  so neither shell metacharacters nor option injection (``--upload-pack=...``)
  can escape.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMEOUT = 60

#: git subcommands ProofLoop is ever allowed to invoke. Read-only by design.
ALLOWED_GIT_SUBCOMMANDS = frozenset(
    {
        "rev-parse",
        "cat-file",
        "status",
        "show",
        "diff-tree",
        "rev-list",
    }
)

#: A git object-ish token: sha, branch, tag, ``HEAD~2``. Deliberately narrow.
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@^~-]{0,255}$")

#: A full or abbreviated hex sha.
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{4,40}$")


class UnsafeCommand(ValueError):
    """Raised when a command or token fails the safety allow-list."""


class UnsafePath(ValueError):
    """Raised when a path would resolve outside the repository root."""


def validate_ref(ref: str) -> str:
    """Return ``ref`` unchanged, or raise :class:`UnsafeCommand`.

    Rejects empty tokens, anything with shell metacharacters or whitespace,
    and anything starting with ``-`` (which git would read as an option).
    """
    if not isinstance(ref, str) or not ref:
        raise UnsafeCommand("empty or non-string git ref")
    if not REF_PATTERN.match(ref):
        raise UnsafeCommand(f"unsafe git ref: {ref!r}")
    if ".." in ref:
        raise UnsafeCommand(f"range/traversal not allowed in ref: {ref!r}")
    return ref


def validate_sha(sha: str) -> str:
    if not isinstance(sha, str) or not SHA_PATTERN.match(sha or ""):
        raise UnsafeCommand(f"not a valid object sha: {sha!r}")
    return sha


def _check_argv(argv: list[str]) -> None:
    if not argv:
        raise UnsafeCommand("empty command")
    for token in argv:
        if not isinstance(token, str):
            raise UnsafeCommand(f"non-string argv token: {token!r}")
        if "\x00" in token or "\n" in token:
            raise UnsafeCommand("argv token contains a control character")

    head = argv[0]
    if head == "git":
        if len(argv) < 2 or argv[1] not in ALLOWED_GIT_SUBCOMMANDS:
            raise UnsafeCommand(f"git subcommand not allow-listed: {argv[1:2]}")
        return
    if head == sys.executable and argv[1:3] == ["-m", "pytest"]:
        return
    raise UnsafeCommand(f"executable not allow-listed: {head!r}")


def safe_run(
    argv: list[str],
    cwd: Path | str,
    timeout: int = DEFAULT_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """Run an allow-listed command with ``shell=False``.

    Raises :class:`UnsafeCommand` before spawning anything if the command is
    not on the allow-list.
    """
    _check_argv(argv)
    return subprocess.run(  # noqa: S603 - argv is allow-listed, shell=False
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )


__all__ = [
    "ALLOWED_GIT_SUBCOMMANDS",
    "DEFAULT_TIMEOUT",
    "UnsafeCommand",
    "UnsafePath",
    "safe_run",
    "validate_ref",
    "validate_sha",
]
