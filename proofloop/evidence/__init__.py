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
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_TIMEOUT = 60

#: The exact git argv shapes ProofLoop emits, minus the caller-supplied ref.
#: A subcommand allow-list is not enough: git accepts write-capable options on
#: read-only subcommands (``git show --output=/tmp/x HEAD`` writes outside the
#: repository), so the whole argv is matched, option by option.
#:
#: ``REF`` marks the one position a validated commit-ish may occupy.
GIT_ARGV_GRAMMARS: tuple[tuple[str, ...], ...] = (
    ("rev-parse", "--is-inside-work-tree"),
    ("rev-parse", "--verify", "REF"),
    ("cat-file", "-e", "REF"),
    ("status", "--porcelain"),
    ("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", "REF"),
)

#: Derived from the grammars above, kept for callers that only want the names.
#: ``show`` and ``rev-list`` were listed here once but are not called by any
#: production path, so they are gone.
ALLOWED_GIT_SUBCOMMANDS = frozenset(grammar[0] for grammar in GIT_ARGV_GRAMMARS)

#: A git object-ish token: sha, branch, tag, ``HEAD~2``. Deliberately narrow.
REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@^~-]{0,255}$")

#: A full or abbreviated hex sha.
SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{4,40}$")

#: A pytest node id: ``tests/test_x.py`` or ``tests/test_x.py::test_case``.
NODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_./:\[\]-]{1,300}$")

#: A Windows drive qualifier at the start of a path: ``C:``, ``c:/``.
DRIVE_PATTERN = re.compile(r"^[A-Za-z]:")

#: The only pytest marker expressions ProofLoop may pass: ``foo`` or ``not foo``.
MARKER_PATTERN = re.compile(r"^(not )?[a-z][a-z0-9_]*$")


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


def validate_node_id(node_id: str) -> str:
    """Return ``node_id`` unchanged, or raise :class:`UnsafeCommand`.

    A pytest node id must be *repo-relative*: ``tests/test_x.py`` or
    ``tests/test_x.py::test_case[param-1]``. Refused here, so that every
    caller inherits the rule rather than relying on a separate containment
    check further down:

    * a leading ``-`` (pytest option injection, e.g. ``-p no:cacheprovider``)
    * shell metacharacters and anything else outside NODE_ID_PATTERN
    * ``..`` traversal
    * absolute POSIX paths (``/tmp/test_x.py``)
    * Windows drive-qualified paths (``C:/tmp/test_x.py``, ``C:\\tmp...``)
    * rooted and UNC Windows paths (``\\server\\share...``)
    """
    if not isinstance(node_id, str) or not node_id:
        raise UnsafeCommand("empty pytest node id")
    if node_id.startswith("-"):
        raise UnsafeCommand(f"option-like pytest target rejected: {node_id!r}")

    # Separator check runs before the pattern so that Windows-style targets
    # get a message about being absolute rather than "unsafe character".
    if "\\" in node_id:
        raise UnsafeCommand(f"backslash in pytest node id: {node_id!r}")

    # Only the path part may look path-like; the ``::`` suffix carries the
    # test name and its parameters.
    path_part = node_id.split("::", 1)[0]
    if path_part.startswith(("/", "\\")):
        raise UnsafeCommand(f"absolute pytest node id rejected: {node_id!r}")
    if DRIVE_PATTERN.match(path_part):
        raise UnsafeCommand(f"drive-qualified pytest node id rejected: {node_id!r}")
    if PurePosixPath(path_part).is_absolute() or PureWindowsPath(path_part).is_absolute():
        raise UnsafeCommand(f"absolute pytest node id rejected: {node_id!r}")

    if not NODE_ID_PATTERN.match(node_id):
        raise UnsafeCommand(f"unsafe pytest node id: {node_id!r}")
    if ".." in node_id:
        raise UnsafeCommand(f"traversal in pytest node id: {node_id!r}")
    return node_id


def validate_marker(expression: str) -> str:
    if not isinstance(expression, str) or not MARKER_PATTERN.match(expression or ""):
        raise UnsafeCommand(f"unsafe pytest marker expression: {expression!r}")
    return expression


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
        _check_git_argv(argv)
        return
    if head == sys.executable:
        _check_pytest_argv(argv)
        return
    raise UnsafeCommand(f"executable not allow-listed: {head!r}")


def _check_commit_ish(token: str) -> str:
    """Validate the one caller-supplied token a git grammar may contain.

    ProofLoop only ever passes a commit-ish in the peeled ``<ref>^{commit}``
    form, or a bare ref to ``diff-tree``. Both go through
    :func:`validate_ref`, so options can never appear in a ref slot.
    """
    if token.endswith("^{commit}"):
        validate_ref(token[: -len("^{commit}")])
        return token
    validate_ref(token)
    return token


def _check_git_argv(argv: list[str]) -> None:
    """Match the argv against :data:`GIT_ARGV_GRAMMARS`, exactly.

    Every option must be one this grammar names, in this position. That is
    what makes the allow-list read-only in practice: ``--output=``,
    ``--exec-path=``, ``--git-path``, ``--filters``, ``--untracked-files=``
    and a pre-subcommand ``-c core.pager=...`` all fail here, before anything
    is spawned.
    """
    rest = argv[1:]
    if not rest:
        raise UnsafeCommand("git invoked without a subcommand")

    for grammar in GIT_ARGV_GRAMMARS:
        if len(rest) != len(grammar):
            continue
        if any(
            expected != "REF" and expected != actual
            for expected, actual in zip(grammar, rest)
        ):
            continue
        for expected, actual in zip(grammar, rest):
            if expected == "REF":
                _check_commit_ish(actual)
        return

    raise UnsafeCommand(f"git argv not allow-listed: {rest}")


def _check_pytest_argv(argv: list[str]) -> None:
    """Allow exactly one pytest argv shape, not "anything starting with pytest".

    Permitted grammar::

        <python> -m pytest -q [-m <marker expr>] [-- <node id>]

    Anything else -- ``-p``, ``--basetemp=``, ``--rootdir=``, ``-c``, bare
    paths, repeated options, trailing junk -- is refused. This is what makes
    the allow-list an allow-list rather than a prefix match.
    """
    if argv[1:4] != ["-m", "pytest", "-q"]:
        raise UnsafeCommand(f"pytest argv not allow-listed: {argv[1:4]}")

    rest = argv[4:]

    if rest[:1] == ["-m"]:
        if len(rest) < 2:
            raise UnsafeCommand("pytest -m given without a marker expression")
        validate_marker(rest[1])
        rest = rest[2:]

    if rest[:1] == ["--"]:
        if len(rest) != 2:
            raise UnsafeCommand(f"pytest target list not allow-listed: {rest[1:]}")
        validate_node_id(rest[1])
        rest = rest[2:]

    if rest:
        raise UnsafeCommand(f"unrecognised pytest arguments: {rest}")


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
    "DRIVE_PATTERN",
    "GIT_ARGV_GRAMMARS",
    "MARKER_PATTERN",
    "NODE_ID_PATTERN",
    "UnsafeCommand",
    "UnsafePath",
    "safe_run",
    "validate_marker",
    "validate_node_id",
    "validate_ref",
    "validate_sha",
]
