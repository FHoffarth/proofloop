"""Tests for the 5-minute showcase demo module."""

from __future__ import annotations

from rich.console import Console

from proofloop.cli import EXIT_BLOCKED, EXIT_PASS, EXIT_REVIEW, main
from proofloop.demo import run_demo
from proofloop.schemas import GateResult, JudgeVerdictValue


def test_run_demo_all_scenarios() -> None:
    code, reports = run_demo(scenario_filter="all", console=Console(quiet=True))
    assert len(reports) == 3
    assert code == EXIT_BLOCKED  # highest exit code among the 3 is 2 (blocked)
    assert reports[0].final_gate.result is GateResult.BLOCKED
    assert reports[1].final_gate.result is GateResult.REVIEW_REQUIRED
    assert reports[2].final_gate.result is GateResult.PASS


def test_run_demo_individual_scenarios() -> None:
    # 1. Blocked
    code, reports = run_demo(scenario_filter="blocked", console=Console(quiet=True))
    assert code == EXIT_BLOCKED
    assert len(reports) == 1
    assert reports[0].pre_gate.result is GateResult.BLOCKED
    assert reports[0].judge is not None and reports[0].judge.skipped is True

    # 2. Review required
    code, reports = run_demo(scenario_filter="review", console=Console(quiet=True))
    assert code == EXIT_REVIEW
    assert len(reports) == 1
    assert reports[0].judge is not None
    assert reports[0].judge.verdict is JudgeVerdictValue.ACCEPT
    assert reports[0].final_gate.result is GateResult.REVIEW_REQUIRED

    # 3. Pass
    code, reports = run_demo(scenario_filter="pass", console=Console(quiet=True))
    assert code == EXIT_PASS
    assert len(reports) == 1
    assert reports[0].final_gate.result is GateResult.PASS


def test_run_demo_unknown_scenario() -> None:
    code, reports = run_demo(scenario_filter="unknown", console=Console(quiet=True))
    assert code == EXIT_BLOCKED
    assert reports == []


def test_cli_demo_command(capsys) -> None:
    assert main(["demo", "--scenario", "pass"]) == EXIT_PASS
    assert main(["demo", "--scenario", "review"]) == EXIT_REVIEW
    assert main(["demo", "--scenario", "blocked"]) == EXIT_BLOCKED


def test_cli_demo_json_output(capsys) -> None:
    assert main(["demo", "--scenario", "pass", "--json"]) == EXIT_PASS
    out = capsys.readouterr().out
    assert "final_gate" in out
    assert "PASS" in out
