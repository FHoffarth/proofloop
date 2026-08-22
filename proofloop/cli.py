"""Command line interface.

    proofloop solve "problem" --repo . --profile verify-commit

Exit codes are the contract:

    0 = PASS
    1 = REVIEW_REQUIRED
    2 = BLOCKED or pipeline failure
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from rich.console import Console

from .orchestrator import Orchestrator
from .profiles import PROFILES
from .providers import ProviderUnavailable
from .registry import available_providers, get_provider
from .render import render_json, render_report

EXIT_PASS = 0
EXIT_REVIEW = 1
EXIT_BLOCKED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proofloop",
        description="Evidence-first verification of engineering claims.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    solve = sub.add_parser("solve", help="run the pipeline over a problem statement")
    solve.add_argument("problem", help="what should be verified")
    solve.add_argument("--repo", default=".", help="repository root (default: .)")
    solve.add_argument(
        "--profile",
        default="quick-check",
        choices=sorted(PROFILES),
        help="workflow profile (default: quick-check)",
    )
    solve.add_argument("--commit", help="commit for verify-commit / verify-fix")
    solve.add_argument(
        "--file",
        dest="files",
        action="append",
        default=[],
        help="repeatable: file the commit must touch",
    )
    solve.add_argument("--path", help="file to inspect (inspect-file)")
    solve.add_argument("--contains", help="text the inspected file must contain")
    solve.add_argument("--branch", help="branch name for BRANCH_AT_SHA")
    solve.add_argument("--sha", help="expected sha for BRANCH_AT_SHA")
    solve.add_argument("--node-id", help="pytest node id for TEST_PASSED")
    solve.add_argument(
        "--provider",
        default="fake",
        choices=available_providers(),
        help="provider to use (offline foundation: fake only)",
    )
    solve.add_argument("--no-judge", action="store_true", help="skip the judge step")
    solve.add_argument("--json", action="store_true", help="emit the report as JSON")
    solve.add_argument(
        "--test-timeout", type=int, default=300, help="timeout for TEST_PASSED, seconds"
    )

    demo = sub.add_parser(
        "demo", help="run interactive 5-minute showcase of ProofLoop thesis"
    )
    demo.add_argument(
        "--scenario",
        default="all",
        choices=["all", "blocked", "review", "pass"],
        help="demo scenario to run (default: all)",
    )
    demo.add_argument("--json", action="store_true", help="emit JSON reports")

    sub.add_parser("profiles", help="list workflow profiles")
    return parser


def _params(args: argparse.Namespace) -> dict[str, object]:
    commit = args.commit
    if not commit and args.profile in ("verify-commit", "verify-fix"):
        commit = "HEAD"
    return {
        "commit": commit,
        "files": args.files,
        "path": args.path,
        "contains": args.contains,
        "branch": args.branch,
        "sha": args.sha,
        "node_id": args.node_id,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    if args.command == "profiles":
        for name, profile in sorted(PROFILES.items()):
            console.print(f"{name:<14} {profile.description}")
        return EXIT_PASS

    if args.command == "demo":
        from .demo import run_demo
        import json
        exit_code, reports = run_demo(scenario_filter=args.scenario, console=console)
        if args.json:
            console.print_json(
                json.dumps([r.model_dump(mode="json") for r in reports], indent=2)
            )
        return exit_code

    try:
        provider = get_provider(args.provider)
    except ProviderUnavailable as exc:
        console.print(f"[red]error[/red]: {exc}")
        return EXIT_BLOCKED

    orchestrator = Orchestrator(
        repo=args.repo,
        provider=provider,
        use_judge=not args.no_judge,
        test_timeout=args.test_timeout,
    )
    report = orchestrator.run(args.problem, args.profile, _params(args))

    if args.json:
        console.print_json(render_json(report))
    else:
        render_report(report, console=console)

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
