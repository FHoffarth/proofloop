"""Test evidence: run pytest as a subprocess and read its exit code.

The public checker is called ``verify_tests_passed`` rather than
``test_passed`` so that pytest does not try to collect it as a test.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from ..schemas import Evidence
from . import UnsafeCommand, safe_run
from .files import UnsafePath, resolve_in_repo

#: A pytest node id: ``tests/test_x.py`` or ``tests/test_x.py::test_case``.
NODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_./:\[\]-]{1,300}$")


def validate_node_id(node_id: str) -> str:
    """Reject anything that is not a plain pytest node id.

    In particular a leading ``-`` (pytest option injection, e.g.
    ``-p no:cacheprovider``) and shell metacharacters are refused.
    """
    if not isinstance(node_id, str) or not node_id:
        raise UnsafeCommand("empty pytest node id")
    if node_id.startswith("-"):
        raise UnsafeCommand(f"option-like pytest target rejected: {node_id!r}")
    if not NODE_ID_PATTERN.match(node_id):
        raise UnsafeCommand(f"unsafe pytest node id: {node_id!r}")
    if ".." in node_id:
        raise UnsafeCommand(f"traversal in pytest node id: {node_id!r}")
    return node_id


def verify_tests_passed(
    repo_root: Path,
    node_id: str | None = None,
    timeout: int = 300,
    extra_marker: str | None = "not integration",
) -> Evidence:
    """Evidence that the given pytest target passes.

    ``node_id`` is validated and, if it names a file, confined to the repo.
    """
    argv = [sys.executable, "-m", "pytest", "-q"]
    if extra_marker:
        argv += ["-m", extra_marker]

    if node_id:
        try:
            safe_id = validate_node_id(node_id)
            resolve_in_repo(repo_root, safe_id.split("::", 1)[0])
        except (UnsafeCommand, UnsafePath) as exc:
            return Evidence(kind="test_passed", ok=False, detail=f"blocked: {exc}")
        argv += ["--", safe_id]

    try:
        proc = safe_run(argv, cwd=repo_root, timeout=timeout)
    except UnsafeCommand as exc:
        return Evidence(kind="test_passed", command=argv, ok=False, detail=f"blocked: {exc}")
    except subprocess.TimeoutExpired:
        return Evidence(
            kind="test_passed",
            command=argv,
            ok=False,
            detail=f"pytest timed out after {timeout}s",
        )
    except OSError as exc:
        return Evidence(
            kind="test_passed", command=argv, ok=False, detail=f"cannot run pytest: {exc}"
        )

    tail = "\n".join((proc.stdout or "").strip().splitlines()[-15:])
    return Evidence(
        kind="test_passed",
        command=argv,
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        detail=("pytest passed" if proc.returncode == 0 else "pytest did not pass"),
        output=tail[:8000],
    )
