"""Human-readable and machine-readable rendering of a RunReport."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .schemas import GateResult, RunReport, VerificationResult

_RESULT_STYLE = {
    VerificationResult.VERIFIED: "green",
    VerificationResult.FAILED: "red",
    VerificationResult.INSUFFICIENT: "yellow",
    VerificationResult.NOT_CHECKED: "dim",
}

_GATE_STYLE = {
    GateResult.PASS: "bold green",
    GateResult.REVIEW_REQUIRED: "bold yellow",
    GateResult.BLOCKED: "bold red",
}


def render_json(report: RunReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2)


def render_report(report: RunReport, console: Console | None = None) -> None:
    console = console or Console()

    console.print(
        Panel(
            f"[bold]{report.problem}[/bold]\n"
            f"profile: {report.profile}   repo: {report.repo}   "
            f"provider: {report.provider} ({report.provider_calls} call(s))",
            title="ProofLoop",
        )
    )

    table = Table(title="Claims")
    table.add_column("Claim")
    table.add_column("Type")
    table.add_column("Result")
    table.add_column("Confidence")
    table.add_column("Reason", overflow="fold")

    for vc in report.verified:
        style = _RESULT_STYLE.get(vc.result, "")
        result_cell = f"[{style}]{vc.result.value}[/{style}]" if style else vc.result.value
        table.add_row(
            vc.claim.id, vc.claim.type.value, result_cell, vc.confidence.value, vc.reason
        )
    if not report.verified:
        table.add_row("-", "-", "-", "-", "no claims in this plan")
    console.print(table)

    # Failed evidence stays visible.
    failures = [(vc, ev) for vc in report.verified for ev in vc.evidence if not ev.ok]
    if failures:
        ev_table = Table(title="Failed evidence")
        ev_table.add_column("Claim")
        ev_table.add_column("Command", overflow="fold")
        ev_table.add_column("Detail", overflow="fold")
        for vc, ev in failures:
            ev_table.add_row(vc.claim.id, " ".join(ev.command) or "-", ev.detail)
        console.print(ev_table)

    for note in report.critique_notes:
        console.print(f"[dim]{note}[/dim]")

    pre_style = _GATE_STYLE[report.pre_gate.result]
    console.print(f"Pre-gate:  [{pre_style}]{report.pre_gate.result.value}[/{pre_style}]")

    if report.judge is not None:
        if report.judge.skipped:
            console.print(f"Judge:     [dim]SKIPPED[/dim] ({report.judge.skip_reason})")
        else:
            console.print(f"Judge:     {report.judge.verdict.value} (advisory)")

    final_style = _GATE_STYLE[report.final_gate.result]
    console.print(f"Gate:      [{final_style}]{report.final_gate.result.value}[/{final_style}]")

    for blocker in report.final_gate.blockers:
        console.print(f"  [red]blocker[/red]: {blocker}")
    for item in report.final_gate.review_items:
        console.print(f"  [yellow]review[/yellow]: {item}")
    for err in report.errors:
        console.print(f"  [red]error[/red]: {err}")

    console.print(f"exit code: {report.exit_code}")
