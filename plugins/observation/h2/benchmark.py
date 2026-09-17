#!/usr/bin/env python3
"""H2.0 real-session benchmark — run deliberately, never in the unit suite.

This script reads the observation ledger written by the H2.0 middleware and
prints the first-real-run report. It drives no browser itself: you drive the
browser (or let a real agent session run), with the mode set to ``observe``,
then run this to read the results.

Usage::

    # 1. enable observation for browser_click only
    export HERMES_BROWSER_ACTION_VERIFICATION=observe

    # 2. ... run your real agent session (>= 50 browser_click calls) ...

    # 3. read the report
    python plugins/observation/h2/benchmark.py
    python plugins/observation/h2/benchmark.py --task-id my-session
    python plugins/observation/h2/benchmark.py --json report.json

Exit code is 0 unless the target sample size is not reached, which makes this
usable as a CI/pre-experiment gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.observation import (  # noqa: E402
    DecisionLedger,
    EvidenceQuality,
    MetricsReport,
    VerificationMode,
    compute_metrics,
    ledger_dir,
)

TARGET_SAMPLE = 50


def load_entries(task_id: str | None):
    """Load ledger entries for one task, or every task in the ledger dir."""
    entries = []
    if task_id:
        return DecisionLedger(
            task_id=task_id, mode=VerificationMode.OBSERVE
        ).read_from_disk()

    for path in sorted(ledger_dir().glob("*.jsonl")):
        ledger = DecisionLedger(task_id=path.stem, mode=VerificationMode.OBSERVE)
        entries.extend(ledger.read_from_disk())
    return entries


def format_report(report: MetricsReport, clicks: list) -> str:
    """Render the exact first-real-run report requested for H2.0-005."""
    total = report.total_actions
    click_count = len(clicks)
    click_errors = sum(1 for e in clicks if e.tool_reported_success is False)
    h2_errors = sum(
        1 for e in clicks if e.error and e.tool_reported_success is not False
    )

    by_type: dict[str, dict[str, int]] = {}
    for entry in clicks:
        bucket = by_type.setdefault(entry.action_type, {})
        bucket[entry.final_verdict] = bucket.get(entry.final_verdict, 0) + 1

    pct = lambda n, d: f"{(n / d * 100):.1f}%" if d else "n/a"  # noqa: E731

    lines = [
        "═" * 62,
        "  H2.0 — RAPPORT DE PREMIÈRE EXÉCUTION RÉELLE",
        "═" * 62,
        "",
        f"  total browser_click ............. {click_count}",
        f"  observable ...................... {total - report.unobservable}  ({pct(total - report.unobservable, total)})",
        f"  unverifiable .................... {report.unobservable}  ({pct(report.unobservable, total)})",
        "",
        f"  VERIFIED ........................ {report.verified}  ({pct(report.verified, total)})",
        f"  UNKNOWN ......................... {report.unknown}  ({pct(report.unknown, total)})",
        f"  FAILED .......................... {report.failed}  ({pct(report.failed, total)})",
        "",
        f"  vision escalations .............. {report.vision_escalations}  ({pct(report.vision_escalations, total)})",
        f"  vision resolution rate .......... {report.vision_resolution_rate:.1%}",
        f"  obstacles detected .............. {report.obstacles_detected}",
        "",
        "  ── LATENCE (séparée : action vs surcoût H2.0) ──",
        f"  action moyenne .................. {report.average_action_latency} ms",
        f"  surcoût H2.0 moyen .............. {report.average_overhead} ms",
        f"  surcoût H2.0 p50 ................ {report.p50_overhead} ms",
        f"  surcoût H2.0 p95 ................ {report.p95_overhead} ms",
        f"  surcoût H2.0 max ................ {report.max_overhead} ms",
        f"  (dont snapshot before/after ..... {report.average_snapshot_before_ms} / {report.average_snapshot_after_ms} ms)",
        "",
        "  ── ERREURS ──",
        f"  erreurs H2.0 .................... {h2_errors}",
        f"  erreurs browser_click ........... {click_errors}",
        "",
        "  ── VERDICTS PAR TYPE D'ACTION ──",
    ]
    for action, verdicts in sorted(by_type.items()):
        detail = "  ".join(f"{k}={v}" for k, v in sorted(verdicts.items()))
        lines.append(f"    {action:22} {detail}")

    lines += [
        "",
        "  ── QUALITÉ D'ÉVIDENCE ──",
    ]
    for quality, count in sorted(report.quality_by_verdict.items()):
        lines.append(f"    {quality:22} {count}")

    lines += [
        "",
        "═" * 62,
        "  ⚠️  VERIFIED est l'OPINION de H2.0, pas la vérité terrain.",
        "      Aucun faux-positif n'est calculable sans ground_truth post-hoc.",
        "═" * 62,
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="H2.0 real-session benchmark report")
    parser.add_argument("--task-id", help="Read a single task's ledger")
    parser.add_argument("--json", help="Also write the raw report as JSON")
    parser.add_argument(
        "--target",
        type=int,
        default=TARGET_SAMPLE,
        help=f"Desired sample size (default {TARGET_SAMPLE})",
    )
    args = parser.parse_args()

    entries = load_entries(args.task_id)
    if not entries:
        print(f"Aucune entrée dans {ledger_dir()}.")
        print("Active d'abord : export HERMES_BROWSER_ACTION_VERIFICATION=observe")
        return 1

    clicks = [e for e in entries if e.action_type == "browser_click"]
    report = compute_metrics(clicks)

    print(format_report(report, clicks))

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"report": report.to_dict(), "entries": [e.to_dict() for e in clicks]},
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        print(f"\n  JSON écrit → {args.json}")

    if len(clicks) < args.target:
        print(
            f"\n  ⚠️  {len(clicks)}/{args.target} clics — échantillon trop petit pour conclure."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
