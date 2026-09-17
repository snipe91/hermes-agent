"""H2.0 benchmarks — 10 synthetic scenarios.

⚠️ IMPORTANT — these are SYNTHETIC and in-process.

They exercise the decision logic and the latency plumbing deterministically.
They do NOT represent real browser performance: there is no browser, no
network, no rendering, and the "slow page" scenario is a sleep, not a real
slow page. Real numbers must come from an actual OBSERVE run (see
``tools/benchmark_h2.py``).

What these tests DO establish, and are worth trusting:
    - the verdict each scenario produces
    - how many vision calls each scenario triggers
    - that the latency breakdown adds up and keeps action time separate
    - that overhead accounting never absorbs action time
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from agent.observation import (
    DecisionLedger,
    EvidenceQuality,
    MetricsCollector,
    VerificationMode,
    begin_observation,
    end_observation,
)
from agent.perception.world_state import WorldState
from agent.verification import ExpectedTransition


# ── scenario definition ───────────────────────────────────────────────────
@dataclass
class Scenario:
    key: str
    label: str
    before: WorldState
    after: WorldState
    expected: ExpectedTransition | None
    observers_delay_ms: float = 0.0  # simulated snapshot cost
    action_exc: Exception | None = None
    vision: str | None = None  # analysis text, or None for "no vision"
    success: bool = True


def _s(**kw) -> WorldState:
    base: dict = {"task_id": "bench"}
    base.update(kw)
    return WorldState(**base)


_BEFORE = _s(
    url="https://app.test/page", accessibility_snapshot="heading Page\nbutton Menu"
)
_AFTER_NAV = _s(url="https://app.test/next", accessibility_snapshot="heading Next")
_AFTER_DOM = _s(
    url="https://app.test/page",
    accessibility_snapshot="heading Page\nbutton Menu\nmenu Options",
    element_count=3,
)
_AFTER_SAME = _s(
    url="https://app.test/page", accessibility_snapshot="heading Page\nbutton Menu"
)
_AFTER_OVERLAY = _s(
    url="https://app.test/page",
    accessibility_snapshot="heading Page\nbutton Menu",
    overlays=({"type": "modal", "label": "Cookies"},),
)
_AFTER_LOADING = _s(
    url="https://app.test/page",
    accessibility_snapshot="heading Page\nLoading… please wait",
    loading=True,
)

SCENARIOS: list[Scenario] = [
    Scenario(
        "A",
        "clic simple",
        _BEFORE,
        _AFTER_DOM,
        ExpectedTransition(description="ouvrir le menu", expect_dom_change=True),
    ),
    Scenario(
        "B",
        "menu dynamique",
        _BEFORE,
        _AFTER_DOM,
        ExpectedTransition(description="ouvrir un menu", expect_dom_change=True),
        observers_delay_ms=3.0,
    ),
    Scenario(
        "C",
        "modal",
        _BEFORE,
        _AFTER_OVERLAY,
        ExpectedTransition(
            description="ouvrir un dialogue",
            expect_dom_change=True,
            expect_no_obstacles=False,
        ),
    ),
    Scenario(
        "D",
        "navigation",
        _BEFORE,
        _AFTER_NAV,
        ExpectedTransition(
            description="aller à la page suivante",
            expect_url_change=True,
            expect_url_contains="next",
        ),
    ),
    Scenario(
        "E",
        "changement DOM sans navigation",
        _BEFORE,
        _AFTER_DOM,
        ExpectedTransition(expect_dom_change=True, expect_url_change=False),
    ),
    Scenario(
        "F",
        "aucun changement",
        _BEFORE,
        _AFTER_SAME,
        ExpectedTransition(description="ouvrir le menu", expect_dom_change=True),
        vision=None,
    ),
    Scenario(
        "G",
        "overlay",
        _BEFORE,
        _AFTER_OVERLAY,
        ExpectedTransition(expect_dom_change=True, expect_no_obstacles=True),
        vision="Un bandeau cookies bloque la page.",
    ),
    Scenario(
        "H",
        "page lente",
        _BEFORE,
        _AFTER_LOADING,
        ExpectedTransition(description="naviguer", expect_url_change=True),
        observers_delay_ms=5.0,
        vision="La page est en cours de chargement.",
    ),
    Scenario(
        "I",
        "erreur d'action",
        _BEFORE,
        _AFTER_SAME,
        None,
        action_exc=RuntimeError("element not found"),
        success=False,
    ),
    Scenario(
        "J",
        "action à risque élevé",
        _BEFORE,
        _AFTER_DOM,
        ExpectedTransition(
            description="confirmer la suppression", expect_dom_change=True
        ),
        observers_delay_ms=2.0,
    ),
]


# ── fakes ─────────────────────────────────────────────────────────────────
class ScriptedObserver:
    """Returns before, then after, with an optional simulated delay."""

    def __init__(self, before, after, delay_ms=0.0):
        self._states = (before, after)
        self._i = 0
        self._delay = delay_ms / 1000.0
        self.calls = 0

    def capture(self, **kwargs):  # noqa: ARG002
        import time

        if self._delay:
            time.sleep(self._delay)
        state = self._states[min(self._i, 1)]
        self._i += 1
        self.calls += 1
        return state


class CountingVision:
    def __init__(self, analysis):
        self.calls = 0
        self._analysis = analysis

    def __call__(self, question="", annotate=False, task_id=None):  # noqa: ARG002
        self.calls += 1
        return json.dumps({
            "success": True,
            "analysis": self._analysis,
            "screenshot_path": "/tmp/bench.png",
        })


def run_scenario(scenario: Scenario, policy, tmp_path):
    """Drive one scenario through the real observation pipeline."""
    ledger = DecisionLedger(task_id=scenario.key, directory=tmp_path)
    observer = ScriptedObserver(
        scenario.before, scenario.after, scenario.observers_delay_ms
    )
    vision = CountingVision(scenario.vision or "Rien de particulier.")

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e1"},
        scenario.key,
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
        expected=scenario.expected,
        risk=None,
    )
    assert ctx is not None

    action_latency = 5.0  # simulated: the action itself is not what we measure here
    result = None
    if scenario.action_exc is not None:
        result = None
    else:
        result = json.dumps({"success": True})

    end_observation(
        ctx,
        result,
        success=scenario.success,
        error=str(scenario.action_exc) if scenario.action_exc else None,
        action_latency_ms=action_latency,
        observer=observer,
        policy=policy,
        runner=vision,
        vision_available=True,
    )

    entries = ledger.entries()
    return (entries[0] if entries else None), vision.calls, observer.calls


# ── the benchmark table ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=[f"{s.key}-{s.label}" for s in SCENARIOS],
)
def test_scenario_verdict_and_vision_calls(scenario, tmp_path):
    """Each scenario must produce a defensible verdict and vision count."""
    from agent.perception.vision_escalation import EscalationPolicy, RiskLevel

    policy = EscalationPolicy(min_risk=RiskLevel.MEDIUM)
    entry, vision_calls, snapshot_calls = run_scenario(scenario, policy, tmp_path)

    assert entry is not None, "every scenario must produce a ledger entry"
    assert snapshot_calls == 2, "before + after observation always happen"

    # Expected verdicts, per scenario. Established by construction, so a change
    # here means the decision logic changed — which is exactly what we want to
    # notice.
    EXPECTED = {
        "A": ("verified", 0),  # DOM changed as claimed
        "B": ("verified", 0),
        # C: the modal adds an *overlay*, which does not alter the
        # accessibility tree, so `expect_dom_change=True` is violated.
        # FAILED is correct: the click did not produce the claimed change.
        # (Overlays optionally permitting is separately covered by G.)
        "C": ("failed", 0),
        "D": ("verified", 0),  # URL changed and contains "next"
        "E": ("verified", 0),
        "F": ("failed", 0),  # claimed a change, none happened
        "G": ("failed", 0),  # obstacle appeared and was not allowed
        "H": ("unknown", 1),  # still loading -> escalated -> inconclusive
        "I": ("unknown", 1),  # action failed, no claim -> UNKNOWN -> vision
        "J": ("verified", 0),
    }
    want_verdict, want_vision = EXPECTED[scenario.key]

    assert entry.final_verdict == want_verdict, (
        f"{scenario.key} ({scenario.label}): got {entry.final_verdict}, expected {want_verdict}"
    )
    assert vision_calls == want_vision, (
        f"{scenario.key} ({scenario.label}): {vision_calls} vision calls, expected {want_vision}"
    )


def test_overhead_never_absorbs_action_time(tmp_path):
    """The core accounting invariant: two separate latency families."""
    from agent.perception.vision_escalation import EscalationPolicy

    entry, _, _ = run_scenario(SCENARIOS[0], EscalationPolicy(), tmp_path)

    assert entry is not None
    # Action time is reported verbatim from the caller...
    assert entry.action_latency_ms == 5.0
    # ...and the overhead is the sum of H2.0's own phases only.
    computed = (
        entry.snapshot_before_ms
        + entry.snapshot_after_ms
        + entry.verification_latency_ms
        + entry.vision_latency_ms
    )
    assert entry.total_observation_overhead_ms == pytest.approx(computed, abs=1e-6)
    # The two families must not be conflated.
    assert entry.total_observation_overhead_ms != entry.action_latency_ms


def test_slow_observer_inflates_overhead_not_action_time(tmp_path):
    """A slow snapshot shows up in overhead, never in action latency."""
    from agent.perception.vision_escalation import EscalationPolicy

    slow = Scenario(
        "SLOW",
        "snapshot lent",
        _BEFORE,
        _AFTER_DOM,
        ExpectedTransition(expect_dom_change=True),
        observers_delay_ms=20.0,
    )
    entry, _, _ = run_scenario(slow, EscalationPolicy(), tmp_path)

    assert entry is not None
    assert entry.action_latency_ms == 5.0  # unchanged
    assert entry.snapshot_before_ms >= 15.0  # the delay is visible here
    assert entry.total_observation_overhead_ms >= 30.0


def test_benchmark_run_produces_a_report(tmp_path):
    """Aggregate a full pass of the 10 scenarios into metrics."""
    from agent.perception.vision_escalation import EscalationPolicy, RiskLevel

    policy = EscalationPolicy(min_risk=RiskLevel.MEDIUM)
    collector = MetricsCollector()

    for scenario in SCENARIOS:
        entry, _, _ = run_scenario(scenario, policy, tmp_path)
        if entry is not None:
            collector.add(entry)

    report = collector.report()

    assert report.total_actions == 10
    assert report.verified + report.failed + report.unknown == 10
    assert report.vision_escalations >= 1
    # Latency families are both populated and distinct.
    assert report.average_action_latency == 5.0
    assert report.average_overhead >= 0.0
    assert report.p95_overhead >= report.p50_overhead
    assert report.p50_action_latency == 5.0
    json.dumps(report.to_dict())


def test_scenario_failed_action_is_recorded_as_failure(tmp_path):
    """Scenario I: the action raised; observation must still land."""
    from agent.perception.vision_escalation import EscalationPolicy

    entry, _, _ = run_scenario(SCENARIOS[8], EscalationPolicy(), tmp_path)

    assert entry is not None
    assert entry.tool_reported_success is False
    assert entry.error is not None


def test_scenario_synthetic_disclaimer_is_present():
    """Guard: the module must state that these numbers are not real-world."""
    doc = __doc__ or ""
    assert "SYNTHETIC" in doc
    assert "do NOT represent real browser performance" in doc


def test_evidence_quality_reflects_the_source(tmp_path):
    """Vision-backed verdicts are labelled visual_heuristic, not structural."""
    from agent.perception.vision_escalation import EscalationPolicy, RiskLevel

    policy = EscalationPolicy(min_risk=RiskLevel.MEDIUM)

    # F fails on structure alone — no vision needed.
    entry_f, vision_f, _ = run_scenario(SCENARIOS[5], policy, tmp_path)
    assert entry_f is not None
    assert vision_f == 0
    assert entry_f.observation_quality == EvidenceQuality.STRUCTURAL.value

    # H is inconclusive structurally, so vision weighs in.
    entry_h, vision_h, _ = run_scenario(SCENARIOS[7], policy, tmp_path)
    assert entry_h is not None
    assert vision_h == 1
    assert entry_h.observation_quality == EvidenceQuality.VISUAL_HEURISTIC.value
