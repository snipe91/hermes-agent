"""Tests for the H2.0 Decision Ledger and Metrics Collector."""

from __future__ import annotations

import json

from agent.observation import (
    DecisionLedger,
    EvidenceQuality,
    LedgerEntry,
    MetricsCollector,
    VerificationMode,
    compute_metrics,
    ledger_dir,
)


def _entry(**kwargs) -> LedgerEntry:
    base: dict = {
        "timestamp": 1_700_000_000.0,
        "task_id": "t1",
        "action_type": "browser_click",
    }
    base.update(kwargs)
    return LedgerEntry(**base)


# ── VerificationMode ──────────────────────────────────────────────────────
def test_mode_parses_valid_values():
    assert VerificationMode.parse("off") is VerificationMode.OFF
    assert VerificationMode.parse("observe") is VerificationMode.OBSERVE
    assert VerificationMode.parse("enforce") is VerificationMode.ENFORCE
    assert VerificationMode.parse(" OBSERVE ") is VerificationMode.OBSERVE


def test_mode_defaults_to_off_for_anything_unknown():
    """An unrecognised value must never enable the experimental layer."""
    assert VerificationMode.parse("banana") is VerificationMode.OFF
    assert VerificationMode.parse(None) is VerificationMode.OFF
    assert VerificationMode.parse(42) is VerificationMode.OFF
    assert VerificationMode.parse({}) is VerificationMode.OFF


def test_mode_accepts_boolean_and_truthy_spellings_as_observe():
    assert VerificationMode.parse(True) is VerificationMode.OBSERVE
    assert VerificationMode.parse(False) is VerificationMode.OFF
    assert VerificationMode.parse("yes") is VerificationMode.OBSERVE
    assert VerificationMode.parse("0") is VerificationMode.OFF


# ── EvidenceQuality ───────────────────────────────────────────────────────
def test_evidence_quality_is_categorical_not_a_probability():
    """Four discrete sources — never a fabricated confidence number."""
    values = {q.value for q in EvidenceQuality}

    assert values == {
        "deterministic",
        "structural",
        "visual_heuristic",
        "unavailable",
    }


# ── LedgerEntry ───────────────────────────────────────────────────────────
def test_ledger_entry_defaults_are_conservative():
    entry = _entry()

    assert entry.final_verdict == "unknown"
    assert entry.initial_verdict == "unknown"
    assert entry.ground_truth is None  # never inferred
    assert entry.vision_escalated is False
    assert entry.observation_quality == EvidenceQuality.UNAVAILABLE.value


def test_ledger_entry_roundtrips_through_json():
    entry = _entry(
        target="@e5",
        risk_level="high",
        before_state_hash="aaa",
        after_state_hash="bbb",
        state_changed=True,
        expected_state_present=True,
        initial_verdict="unknown",
        vision_escalated=True,
        final_verdict="verified",
        obstacles_detected=1,
        observation_quality=EvidenceQuality.VISUAL_HEURISTIC.value,
        latency_ms=42.5,
        vision_latency_ms=1200.0,
    )

    payload = json.loads(json.dumps(entry.to_dict()))
    restored = LedgerEntry.from_dict(payload)

    assert restored.to_dict() == payload


def test_ledger_entry_ignores_unknown_fields_on_restore():
    """A ledger written by a newer version must not crash an older reader."""
    payload = _entry().to_dict()
    payload["some_future_field"] = "value"

    restored = LedgerEntry.from_dict(payload)

    assert restored.action_type == "browser_click"


# ── DecisionLedger ────────────────────────────────────────────────────────
def test_ledger_writes_and_reads_back(tmp_path):
    ledger = DecisionLedger(task_id="sess-1", directory=tmp_path)

    assert ledger.record(_entry(action_type="browser_click"))
    assert ledger.record(_entry(action_type="browser_type"))

    on_disk = ledger.read_from_disk()
    assert len(on_disk) == 2
    assert on_disk[0].action_type == "browser_click"


def test_ledger_failure_never_raises(tmp_path):
    """A broken ledger must not break a tool call."""
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a directory")

    ledger = DecisionLedger(task_id="sess-1", directory=blocker)

    assert ledger.record(_entry()) is False  # reports failure
    assert ledger.write_failures == 1  # and counts it
    # No exception escaped — that is the contract.


def test_ledger_disabled_records_nothing(tmp_path):
    ledger = DecisionLedger(task_id="s", directory=tmp_path, enabled=False)

    assert ledger.record(_entry()) is False
    assert ledger.entries() == []
    assert ledger.read_from_disk() == []


def test_ledger_skips_corrupt_lines(tmp_path):
    ledger = DecisionLedger(task_id="s", directory=tmp_path)
    ledger.record(_entry())

    path = ledger.path()
    with path.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")

    ledger.record(_entry())

    restored = ledger.read_from_disk()
    assert len(restored) == 2  # the corrupt line is skipped, not fatal


def test_ledger_sanitises_task_id(tmp_path):
    ledger = DecisionLedger(task_id="../../etc/passwd", directory=tmp_path)

    assert ".." not in ledger.path().name
    assert "/" not in ledger.path().name


def test_ledger_dir_is_under_hermes_home():
    path = str(ledger_dir())

    assert "hermes" in path.lower() or "h2" in path.lower()


# ── Metrics ───────────────────────────────────────────────────────────────
def test_metrics_on_empty_input_are_zero_not_nan():
    report = compute_metrics([])

    assert report.total_actions == 0
    assert report.escalation_rate == 0.0
    assert report.observable_rate == 0.0
    assert report.vision_resolution_rate == 0.0
    assert report.average_verification_latency == 0.0


def test_metrics_tally_verdicts():
    report = compute_metrics([
        _entry(final_verdict="verified"),
        _entry(final_verdict="verified"),
        _entry(final_verdict="failed"),
        _entry(final_verdict="unknown"),
    ])

    assert report.total_actions == 4
    assert report.verified == 2
    assert report.failed == 1
    assert report.unknown == 1


def test_metrics_tally_vision_outcomes():
    report = compute_metrics([
        _entry(
            vision_escalated=True,
            final_verdict="verified",
            observation_quality=EvidenceQuality.VISUAL_HEURISTIC.value,
            vision_latency_ms=1000.0,
        ),
        _entry(
            vision_escalated=True,
            final_verdict="unknown",
            observation_quality=EvidenceQuality.VISUAL_HEURISTIC.value,
            vision_latency_ms=2000.0,
        ),
        _entry(vision_escalated=False),
    ])

    assert report.vision_escalations == 2
    assert report.vision_successes == 1
    assert report.vision_failures == 1
    assert report.average_vision_latency == 1500.0
    assert report.escalation_rate == round(2 / 3, 4)


def test_metrics_group_by_risk_and_action_type():
    report = compute_metrics([
        _entry(
            action_type="browser_click", risk_level="high", final_verdict="verified"
        ),
        _entry(action_type="browser_click", risk_level="low", final_verdict="unknown"),
        _entry(
            action_type="browser_navigate",
            risk_level="medium",
            final_verdict="verified",
        ),
    ])

    assert report.actions_by_risk == {"high": 1, "low": 1, "medium": 1}
    assert report.verdicts_by_action_type["browser_click"] == {
        "verified": 1,
        "unknown": 1,
    }
    assert report.verdicts_by_risk["high"] == {"verified": 1}


def test_metrics_count_errors_and_obstacles():
    report = compute_metrics([
        _entry(error="boom", obstacles_detected=2),
        _entry(obstacles_detected=1),
    ])

    assert report.verification_errors == 1
    assert report.obstacles_detected == 3


def test_metrics_observable_rate_uses_quality():
    report = compute_metrics([
        _entry(observation_quality=EvidenceQuality.STRUCTURAL.value),
        _entry(observation_quality=EvidenceQuality.UNAVAILABLE.value),
        _entry(observation_quality=EvidenceQuality.STRUCTURAL.value),
        _entry(observation_quality=EvidenceQuality.UNAVAILABLE.value),
    ])

    assert report.unobservable == 2
    assert report.observable_rate == 0.5


def test_metrics_latency_average_and_max():
    report = compute_metrics([
        _entry(latency_ms=10.0),
        _entry(latency_ms=30.0),
        _entry(latency_ms=20.0),
    ])

    assert report.average_verification_latency == 20.0
    assert report.max_verification_latency == 30.0


def test_metrics_never_invent_ground_truth():
    """Without ground truth, false positives are reported as UNVERIFIABLE."""
    report = compute_metrics([_entry(final_verdict="verified")])

    assert report.entries_with_ground_truth == 0
    assert report.unverifiable_verified == 0  # nothing claimed, nothing counted


def test_metrics_counts_false_verified_when_ground_truth_exists():
    report = compute_metrics([
        _entry(final_verdict="verified", ground_truth="failed"),
        _entry(final_verdict="verified", ground_truth="verified"),
    ])

    assert report.entries_with_ground_truth == 2
    assert report.unverifiable_verified == 1


def test_metrics_report_is_json_safe():
    report = compute_metrics([_entry(final_verdict="verified", vision_escalated=True)])

    json.dumps(report.to_dict())
    assert isinstance(report.summary_lines(), list)


def test_metrics_collector_accumulates():
    collector = MetricsCollector()
    collector.add(_entry(final_verdict="verified"))
    collector.extend([_entry(), _entry()])

    assert collector.count == 3
    assert collector.report().total_actions == 3

    collector.clear()
    assert collector.count == 0
