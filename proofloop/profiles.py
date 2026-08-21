"""Workflow profiles.

Different tasks require different evidence, so the required claim set is
explicit per profile rather than hard-coded globally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .schemas import Claim, ClaimType

PROFILE_NAMES = ("verify-commit", "verify-fix", "inspect-file", "quick-check", "none")


class ProfileError(ValueError):
    """Unknown profile, or a profile invoked without its required inputs."""


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    build: Callable[[dict[str, Any]], list[Claim]]
    requires: tuple[str, ...] = field(default=())

    def claims(self, params: dict[str, Any]) -> list[Claim]:
        missing = [key for key in self.requires if not params.get(key)]
        if missing:
            raise ProfileError(
                f"profile {self.name!r} requires: {', '.join(missing)}"
            )
        return self.build(params)


def _verify_commit(p: dict[str, Any]) -> list[Claim]:
    commit = p["commit"]
    claims = [
        Claim(
            id="commit-exists",
            type=ClaimType.COMMIT_EXISTS,
            statement=f"commit {commit} exists in the repository",
            required=True,
            params={"commit": commit},
        )
    ]
    files = list(p.get("files") or [])
    if files:
        claims.append(
            Claim(
                id="commit-touches-files",
                type=ClaimType.COMMIT_TOUCHES_FILES,
                statement=f"commit {commit} touches {files}",
                required=True,
                params={"commit": commit, "files": files},
            )
        )
    if p.get("branch") and p.get("sha"):
        claims.append(
            Claim(
                id="branch-at-sha",
                type=ClaimType.BRANCH_AT_SHA,
                statement=f"branch {p['branch']} points at {p['sha']}",
                required=True,
                params={"branch": p["branch"], "sha": p["sha"]},
            )
        )
    return claims


def _verify_fix(p: dict[str, Any]) -> list[Claim]:
    commit = p["commit"]
    claims = _verify_commit(p)
    claims.append(
        Claim(
            id="tests-pass",
            type=ClaimType.TEST_PASSED,
            statement="the test suite passes",
            required=True,
            params={"node_id": p.get("node_id")},
        )
    )
    claims.append(
        Claim(
            id="bug-fixed",
            type=ClaimType.BUG_FIXED,
            statement=f"commit {commit} actually fixes the reported bug",
            required=False,
            params={},
        )
    )
    claims.append(
        Claim(
            id="no-regression",
            type=ClaimType.NO_REGRESSION,
            statement="the change introduces no regression",
            required=False,
            params={},
        )
    )
    return claims


def _inspect_file(p: dict[str, Any]) -> list[Claim]:
    return [
        Claim(
            id="file-contains",
            type=ClaimType.FILE_CONTAINS,
            statement=f"{p['path']} contains the expected content",
            required=True,
            params={"path": p["path"], "text": p["contains"]},
        )
    ]


def _quick_check(p: dict[str, Any]) -> list[Claim]:
    return [
        Claim(
            id="worktree-clean",
            type=ClaimType.WORKTREE_CLEAN,
            statement="the working tree is clean",
            required=True,
            params={},
        )
    ]


def _none(p: dict[str, Any]) -> list[Claim]:
    return []


PROFILES: dict[str, Profile] = {
    "verify-commit": Profile(
        name="verify-commit",
        description="Prove a commit exists and, optionally, what it touched.",
        build=_verify_commit,
        requires=("commit",),
    ),
    "verify-fix": Profile(
        name="verify-fix",
        description="verify-commit plus a test run, plus open evaluative claims.",
        build=_verify_fix,
        requires=("commit",),
    ),
    "inspect-file": Profile(
        name="inspect-file",
        description="Prove a repo-internal file contains an expected string.",
        build=_inspect_file,
        requires=("path", "contains"),
    ),
    "quick-check": Profile(
        name="quick-check",
        description="Prove the working tree is clean.",
        build=_quick_check,
    ),
    "none": Profile(
        name="none",
        description="No claims. The gate has nothing to prove and nothing to block.",
        build=_none,
    ),
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ProfileError(
            f"unknown profile {name!r}; available: {', '.join(PROFILES)}"
        ) from None
