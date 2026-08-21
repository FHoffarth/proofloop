"""Test evidence: run pytest as a subprocess and read its exit code.

The public checker is called ``verify_tests_passed`` rather than
``test_passed`` so that pytest does not try to collect it as a test.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..schemas import Evidence
from . import NODE_ID_PATTERN, UnsafeCommand, safe_run, validate_node_id
from .files import UnsafePath, resolve_in_repo

# The node-id validator lives beside the argv allow-list in
# ``proofloop.evidence`` so that safe_run can enforce the same rule on the
# argv it is handed, no matter who built it. Re-exported here for callers.
__all__ = ["NODE_ID_PATTERN", "validate_node_id", "verify_tests_passed"]


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
