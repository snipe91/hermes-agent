"""Hermes 2.0 — Metrics collector.

Aggregates ledger entries into the numbers needed to decide whether H2.0
deserves to alter a trajectory. Pure computation over ``LedgerEntry`` objects —
no I/O, no storage, no side effects.

Scientific stance:
    A VERIFIED verdict is H2.0's *opinion*, not ground truth. This module
    therefore reports false-positive potential as ``unverifiable`` counts rather
    than inventing an accuracy figure it cannot substantiate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .ledger import EvidenceQuality, LedgerEntry


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Deterministic, no interpolation guesswork.

    Args:
        values: Non-empty list of samples.
        pct: Percentile in [0, 100].

    Returns:
        The sample at that rank, or 0.0 for an empty input. No fabricated
        values for missing data.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if pct <= 0:
        return round(ordered[0], 3)
    if pct >= 100:
        return round(ordered[-1], 3)
    import math

    rank = max(0, min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1))
    return round(ordered[rank], 3)


@dataclass
class MetricsReport:
    """Aggregated measurements over a set of decisions."""

    total_actions: int = 0
    verified: int = 0
    failed: int = 0
    unknown: int = 0

    vision_escalations: int = 0
    vision_successes: int = 0
    vision_failures: int = 0

    verification_errors: int = 0
    obstacles_detected: int = 0
    unobservable: int = 0

    average_verification_latency: float = 0.0
    average_vision_latency: float = 0.0
    max_verification_latency: float = 0.0

    # ── Latency separation: the action's own time vs H2.0's added cost ────
    average_action_latency: float = 0.0
    average_overhead: float = 0.0
    p50_overhead: float = 0.0
    p95_overhead: float = 0.0
    max_overhead: float = 0.0
    average_snapshot_before_ms: float = 0.0
    average_snapshot_after_ms: float = 0.0
    p50_action_latency: float = 0.0
    p95_action_latency: float = 0.0

    actions_by_risk: dict[str, int] = field(default_factory=dict)
    verdicts_by_action_type: dict[str, dict[str, int]] = field(default_factory=dict)
    verdicts_by_risk: dict[str, dict[str, int]] = field(default_factory=dict)
    quality_by_verdict: dict[str, int] = field(default_factory=dict)

    escalation_rate: float = 0.0
    observable_rate: float = 0.0
    vision_resolution_rate: float = 0.0

    # Explicitly not a probability: we cannot know how many VERIFIED are wrong.
    unverifiable_verified: int = 0
    entries_with_ground_truth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "verified": self.verified,
            "failed": self.failed,
            "unknown": self.unknown,
            "vision_escalations": self.vision_escalations,
            "vision_successes": self.vision_successes,
            "vision_failures": self.vision_failures,
            "verification_errors": self.verification_errors,
            "obstacles_detected": self.obstacles_detected,
            "unobservable": self.unobservable,
            "average_verification_latency": self.average_verification_latency,
            "average_vision_latency": self.average_vision_latency,
            "max_verification_latency": self.max_verification_latency,
            "average_action_latency": self.average_action_latency,
            "p50_action_latency": self.p50_action_latency,
            "p95_action_latency": self.p95_action_latency,
            "average_overhead": self.average_overhead,
            "p50_overhead": self.p50_overhead,
            "p95_overhead": self.p95_overhead,
            "max_overhead": self.max_overhead,
            "average_snapshot_before_ms": self.average_snapshot_before_ms,
            "average_snapshot_after_ms": self.average_snapshot_after_ms,
            "actions_by_risk": dict(self.actions_by_risk),
            "verdicts_by_action_type": {
                k: dict(v) for k, v in self.verdicts_by_action_type.items()
            },
            "verdicts_by_risk": {k: dict(v) for k, v in self.verdicts_by_risk.items()},
            "quality_by_verdict": dict(self.quality_by_verdict),
            "escalation_rate": self.escalation_rate,
            "observable_rate": self.observable_rate,
            "vision_resolution_rate": self.vision_resolution_rate,
            "unverifiable_verified": self.unverifiable_verified,
            "entries_with_ground_truth": self.entries_with_ground_truth,
        }

    def summary_lines(self) -> list[str]:
        """Compact human-readable summary, for logs and reports."""
        return [
            f"actions={self.total_actions} verified={self.verified} "
            f"failed={self.failed} unknown={self.unknown}",
            f"observable={self.observable_rate:.1%} "
            f"escalation={self.escalation_rate:.1%}",
            f"vision calls={self.vision_escalations} "
            f"resolved={self.vision_resolution_rate:.1%} "
            f"(ok={self.vision_successes} ko={self.vision_failures})",
            f"errors={self.verification_errors} obstacles={self.obstacles_detected}",
            f"latency avg={self.average_verification_latency}ms "
            f"max={self.max_verification_latency}ms "
            f"vision avg={self.average_vision_latency}ms",
        ]


class MetricsCollector:
    """Accumulates ledger entries and computes a report on demand."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def add(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def extend(self, entries: Iterable[LedgerEntry]) -> None:
        self._entries.extend(entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()

    def report(self) -> MetricsReport:
        """Compute the aggregate report. Pure and repeatable."""
        return compute_metrics(self._entries)


def compute_metrics(entries: Iterable[LedgerEntry]) -> MetricsReport:
    """Aggregate a sequence of ledger entries into a ``MetricsReport``.

    Args:
        entries: Decision records, in any order.

    Returns:
        A fully populated report. Rates are 0.0 when the denominator is 0 —
        never NaN, never a fabricated value.
    """
    items = list(entries)
    report = MetricsReport(total_actions=len(items))

    latencies: list[float] = []
    vision_latencies: list[float] = []
    overheads: list[float] = []
    action_latencies: list[float] = []
    before_ms: list[float] = []
    after_ms: list[float] = []

    for entry in items:
        # Verdict tallies
        verdict = (entry.final_verdict or "unknown").lower()
        if verdict == "verified":
            report.verified += 1
        elif verdict == "failed":
            report.failed += 1
        else:
            report.unknown += 1
            verdict = "unknown"

        # Risk tallies
        risk = (entry.risk_level or "medium").lower()
        report.actions_by_risk[risk] = report.actions_by_risk.get(risk, 0) + 1

        by_type = report.verdicts_by_action_type.setdefault(
            entry.action_type or "?", {}
        )
        by_type[verdict] = by_type.get(verdict, 0) + 1

        by_risk = report.verdicts_by_risk.setdefault(risk, {})
        by_risk[verdict] = by_risk.get(verdict, 0) + 1

        quality = entry.observation_quality or EvidenceQuality.UNAVAILABLE.value
        report.quality_by_verdict[quality] = (
            report.quality_by_verdict.get(quality, 0) + 1
        )

        # Vision
        if entry.vision_escalated:
            report.vision_escalations += 1
            if quality == EvidenceQuality.VISUAL_HEURISTIC.value and verdict in {
                "verified",
                "failed",
            }:
                report.vision_successes += 1
            else:
                report.vision_failures += 1
            vision_latencies.append(entry.vision_latency_ms)

        # Errors and obstacles
        if entry.error:
            report.verification_errors += 1
        if entry.obstacles_detected:
            report.obstacles_detected += entry.obstacles_detected
        if quality == EvidenceQuality.UNAVAILABLE.value:
            report.unobservable += 1

        # Ground truth (post-hoc only)
        if entry.ground_truth:
            report.entries_with_ground_truth += 1
            if verdict == "verified" and entry.ground_truth.lower() != "verified":
                report.unverifiable_verified += 1

        latencies.append(entry.latency_ms)

        # Latency separation
        overheads.append(entry.total_observation_overhead_ms)
        action_latencies.append(entry.action_latency_ms)
        before_ms.append(entry.snapshot_before_ms)
        after_ms.append(entry.snapshot_after_ms)

    # Rates
    if report.total_actions:
        report.escalation_rate = round(
            report.vision_escalations / report.total_actions, 4
        )
        report.observable_rate = round(
            (report.total_actions - report.unobservable) / report.total_actions, 4
        )

    if report.vision_escalations:
        report.vision_resolution_rate = round(
            report.vision_successes / report.vision_escalations, 4
        )

    report.average_verification_latency = _mean(latencies)
    report.average_vision_latency = _mean(vision_latencies)
    report.max_verification_latency = round(max(latencies), 3) if latencies else 0.0

    # ── Latency separation ────────────────────────────────────────────────
    # Reported as two distinct families so H2.0's cost is never confused with
    # how long the browser action itself took.
    report.average_action_latency = _mean(action_latencies)
    report.p50_action_latency = _percentile(action_latencies, 50)
    report.p95_action_latency = _percentile(action_latencies, 95)

    report.average_overhead = _mean(overheads)
    report.p50_overhead = _percentile(overheads, 50)
    report.p95_overhead = _percentile(overheads, 95)
    report.max_overhead = round(max(overheads), 3) if overheads else 0.0

    report.average_snapshot_before_ms = _mean(before_ms)
    report.average_snapshot_after_ms = _mean(after_ms)

    return report
