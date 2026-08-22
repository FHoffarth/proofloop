"""Self-contained demo proving ProofLoop's core thesis in under 5 minutes.

Runs three canonical scenarios offline without external dependencies or API keys:
1. The Hallucination Veto: Agent claims a phantom commit; Pre-Gate blocks and skips judge.
2. Advisory vs Authority: Model judge votes ACCEPT; Proof Gate still forces human review.
3. Verified Proof: Deterministic evidence verified; Proof Gate passes.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from .orchestrator import Orchestrator
from .providers import FakeProvider
from .render import render_report
from .schemas import RunReport


@dataclass(frozen=True)
class DemoScenario:
    id: str
    title: str
    thesis: str
    problem: str
    profile: str
    judge_response: str
    expected_gate: str
    expected_exit: int


SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        id="blocked",
        title="Scenario 1: The Hallucination Veto (Deterministic Blocker)",
        thesis=(
            "An agent claims a bug is fixed in commit 'deadbeef...'.\n"
            "ProofLoop checks Git evidence directly. The commit does not exist.\n"
            "Pre-Gate BLOCKS immediately and SKIPS the judge model, saving cost."
        ),
        problem="Agent claims commit deadbeefdeadbeefdeadbeefdeadbeefdeadbeef fixes critical bug",
        profile="verify-commit",
        judge_response="ACCEPT - looks completely fine to me",
        expected_gate="BLOCKED",
        expected_exit=2,
    ),
    DemoScenario(
        id="review",
        title="Scenario 2: Advisory vs Authority (LLM Cannot Override Gate)",
        thesis=(
            "Deterministic checks pass, and the Judge LLM votes ACCEPT.\n"
            "However, evaluative claims ('BUG_FIXED') cannot be proven by models.\n"
            "The Proof Gate overrides model confidence and demands human review."
        ),
        problem="Verify bug fix and regression safety for HEAD",
        profile="verify-fix",
        judge_response="ACCEPT - All code changes look optimal and safe to deploy.",
        expected_gate="REVIEW_REQUIRED",
        expected_exit=1,
    ),
    DemoScenario(
        id="pass",
        title="Scenario 3: Verified Proof (Deterministic Fact Established)",
        thesis=(
            "Working tree is clean and deterministic facts are fully verified.\n"
            "No unresolved evaluative claims remain.\n"
            "The Proof Gate issues a definitive PASS."
        ),
        problem="Verify clean repository state",
        profile="quick-check",
        judge_response="ACCEPT",
        expected_gate="PASS",
        expected_exit=0,
    ),
)


def _init_demo_repo(path: Path) -> str:
    def _git(*args: str) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=path, capture_output=True, text=True, check=True
        )
        return proc.stdout.strip()

    _git("init", "-b", "main")
    _git("config", "user.email", "demo@proofloop.dev")
    _git("config", "user.name", "ProofLoop Demo")
    (path / ".gitignore").write_text(
        "__pycache__/\n.pytest_cache/\n*.pyc\n", encoding="utf-8"
    )
    (path / "app.py").write_text("def solve():\n    return 42\n", encoding="utf-8")
    (path / "test_app.py").write_text(
        "def test_solve():\n    from app import solve\n    assert solve() == 42\n",
        encoding="utf-8",
    )
    _git("add", ".")
    _git("commit", "-m", "initial demo commit")
    return _git("rev-parse", "HEAD")


def run_demo(
    scenario_filter: str = "all",
    console: Console | None = None,
) -> tuple[int, list[RunReport]]:
    """Run demonstration scenarios and render results.

    Returns (highest_exit_code, reports).
    """
    console = console or Console()
    console.print(
        Panel(
            "[bold white]ProofLoop 5-Minute Proof Thesis Demo[/bold white]\n"
            "[dim]Core Law: Agent reports are claims. Git/tests are evidence. "
            "LLM verdicts cannot override deterministic proof gates.[/dim]",
            title="ProofLoop Demo",
            border_style="cyan",
        )
    )

    selected = (
        SCENARIOS
        if scenario_filter == "all"
        else [s for s in SCENARIOS if s.id == scenario_filter]
    )

    if not selected:
        console.print(f"[red]error[/red]: unknown scenario {scenario_filter!r}")
        return 2, []

    reports: list[RunReport] = []
    max_exit = 0

    with tempfile.TemporaryDirectory(prefix="proofloop-demo-") as tmpdir:
        repo_dir = Path(tmpdir)
        head_commit = _init_demo_repo(repo_dir)

        for sc in selected:
            console.print()
            console.print(Rule(f"[bold yellow]{sc.title}[/bold yellow]"))
            console.print(f"[italic]{sc.thesis}[/italic]\n")

            provider = FakeProvider(responses={"judge": sc.judge_response})
            orchestrator = Orchestrator(repo=repo_dir, provider=provider)

            params: dict[str, object] = {}
            if sc.id == "blocked":
                params["commit"] = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
            elif sc.id == "review":
                params["commit"] = head_commit
                params["node_id"] = "test_app.py"

            report = orchestrator.run(sc.problem, sc.profile, params)
            reports.append(report)
            render_report(report, console=console)

            max_exit = max(max_exit, report.exit_code)

    return max_exit, reports
