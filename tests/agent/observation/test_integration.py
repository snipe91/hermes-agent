"""Tests for the H2.0 observation integration (mode OFF / OBSERVE / ENFORCE).

Central contract under test:
    A failure anywhere in H2.0 must never break the agent's existing behaviour.
"""

from __future__ import annotations

import json

from agent.observation import (
    DecisionLedger,
    EvidenceQuality,
    MetricsCollector,
    ObservationContext,
    VerificationMode,
    begin_observation,
    end_observation,
    observation_is_informational_only,
    resolve_mode,
)
from agent.observation.integration import OBSERVABLE_TOOLS
from agent.perception.vision_escalation import EscalationPolicy, RiskLevel
from agent.perception.world_state import WorldState


# ── fakes ─────────────────────────────────────────────────────────────────
class FakeObserver:
    """Returns a scripted sequence of WorldStates."""

    def __init__(self, states, raise_on=None):
        self._states = list(states)
        self._i = 0
        self.calls = 0
        self._raise_on = raise_on

    def capture(self, **kwargs):  # noqa: ARG002
        self.calls += 1
        if self._raise_on is not None and self.calls == self._raise_on:
            raise RuntimeError("observer exploded")
        state = self._states[min(self._i, len(self._states) - 1)]
        self._i += 1
        return state


class CountingVision:
    def __init__(self, analysis=None):
        self.calls = 0
        self._analysis = analysis or "Le dashboard est affiche."

    def __call__(self, question="", annotate=False, task_id=None):  # noqa: ARG002
        self.calls += 1
        return json.dumps({
            "success": True,
            "analysis": self._analysis,
            "screenshot_path": "/tmp/s.png",
        })


def _state(**kwargs) -> WorldState:
    base: dict = {"task_id": "t1"}
    base.update(kwargs)
    return WorldState(**base)


CHANGED = (
    _state(url="https://app.test/a", accessibility_snapshot="button A"),
    _state(url="https://app.test/b", accessibility_snapshot="button A\nmenu B"),
)
UNCHANGED = (
    _state(url="https://app.test/a", accessibility_snapshot="button A"),
    _state(url="https://app.test/a", accessibility_snapshot="button A"),
)


# ── configuration ─────────────────────────────────────────────────────────
def test_resolve_mode_from_config():
    assert (
        resolve_mode({"agent": {"browser_action_verification": "off"}})
        is VerificationMode.OFF
    )
    assert (
        resolve_mode({"agent": {"browser_action_verification": "observe"}})
        is VerificationMode.OBSERVE
    )
    assert (
        resolve_mode({"agent": {"browser_action_verification": "enforce"}})
        is VerificationMode.ENFORCE
    )


def test_resolve_mode_defaults_to_off():
    assert resolve_mode({}) is VerificationMode.OFF
    assert resolve_mode({"agent": {}}) is VerificationMode.OFF
    assert resolve_mode(None) is VerificationMode.OFF


def test_resolve_mode_env_var_wins(monkeypatch):
    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "observe")
    assert (
        resolve_mode({"agent": {"browser_action_verification": "off"}})
        is VerificationMode.OBSERVE
    )

    monkeypatch.setenv("HERMES_BROWSER_ACTION_VERIFICATION", "off")
    assert (
        resolve_mode({"agent": {"browser_action_verification": "enforce"}})
        is VerificationMode.OFF
    )


def test_resolve_mode_ignores_garbage(monkeypatch):
    monkeypatch.delenv("HERMES_BROWSER_ACTION_VERIFICATION", raising=False)
    assert (
        resolve_mode({"agent": {"browser_action_verification": "yes please"}})
        is VerificationMode.OFF
    )


# ── OFF ───────────────────────────────────────────────────────────────────
def test_off_returns_none_and_touches_nothing(tmp_path):
    """OFF: no observation at all — one identity check, nothing else."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(CHANGED)

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e5"},
        "t1",
        mode=VerificationMode.OFF,
        observer=observer,
        ledger=ledger,
    )

    assert ctx is None
    assert observer.calls == 0  # no snapshot taken
    assert ledger.entries() == []  # no ledger event

    evidence = end_observation(ctx, "ok", success=True)
    assert evidence is None
    assert ledger.entries() == []


def test_off_ignores_unobservable_tools():
    assert (
        begin_observation("terminal", {}, "t1", mode=VerificationMode.OBSERVE) is None
    )
    assert (
        begin_observation("read_file", {}, "t1", mode=VerificationMode.OBSERVE) is None
    )


def test_observable_tools_are_browser_actions_only():
    assert OBSERVABLE_TOOLS == {
        "browser_click",
        "browser_type",
        "browser_navigate",
        "browser_press",
    }


# ── OBSERVE ───────────────────────────────────────────────────────────────
def test_observe_records_and_does_not_alter_result(tmp_path):
    """The result the caller passes in is never returned as a modified value."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(CHANGED)
    original = json.dumps({"success": True, "clicked": "@e5"})

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e5"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
    )
    assert ctx is not None

    evidence = end_observation(ctx, original, success=True)

    # The caller keeps its own `original` untouched.
    assert json.loads(original)["clicked"] == "@e5"
    assert evidence is not None
    # Ledger got exactly one record.
    assert len(ledger.entries()) == 1
    entry = ledger.entries()[0]
    assert entry.action_type == "browser_click"
    assert entry.target == "@e5"
    assert entry.mode == VerificationMode.OBSERVE.value
    assert entry.tool_reported_success is True


def test_observe_uses_policy_for_escalation(tmp_path):
    """UNKNOWN + HIGH risk + policy -> exactly one vision call."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(UNCHANGED)  # no structural change -> UNKNOWN
    vision = CountingVision()

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e9"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
        risk=RiskLevel.HIGH,
        expected=None,  # no claim -> UNKNOWN -> escalation candidate
    )
    end_observation(
        ctx,
        "ok",
        success=True,
        observer=observer,
        policy=EscalationPolicy(min_risk=RiskLevel.MEDIUM),
        runner=vision,
        vision_available=True,
    )

    assert vision.calls == 1
    entry = ledger.entries()[0]
    assert entry.vision_escalated is True
    assert entry.initial_verdict == "unknown"
    assert entry.vision_latency_ms >= 0.0


def test_observe_verdict_is_informational_only():
    """OBSERVE must never be treated as permission to act on a verdict."""
    assert observation_is_informational_only(VerificationMode.OFF) is True
    assert observation_is_informational_only(VerificationMode.OBSERVE) is True
    assert observation_is_informational_only(VerificationMode.ENFORCE) is False


# ── ENFORCE ───────────────────────────────────────────────────────────────
def test_enforce_mechanism_can_propagate_a_verdict(tmp_path):
    """ENFORCE wiring works — but is not enabled by default anywhere."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(CHANGED)

    ctx = begin_observation(
        "browser_navigate",
        {"url": "https://app.test/b"},
        "t1",
        mode=VerificationMode.ENFORCE,
        observer=observer,
        ledger=ledger,
    )
    assert ctx is not None
    assert ctx.mode is VerificationMode.ENFORCE

    evidence = end_observation(ctx, "ok", success=True, observer=observer)

    assert evidence is not None
    assert evidence.outcome.value in {"verified", "failed", "unknown"}
    assert evidence.expected is not None  # navigation intent was inferred
    assert ledger.entries()[0].mode == VerificationMode.ENFORCE.value


def test_enforce_is_never_the_default():
    assert resolve_mode({}) is not VerificationMode.ENFORCE
    assert resolve_mode({"agent": {}}) is not VerificationMode.ENFORCE


# ── vision call counts ────────────────────────────────────────────────────
def test_twenty_normal_clicks_zero_vision_calls(tmp_path):
    """20 clicks that structurally change the DOM -> VERIFIED -> no vision."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    vision = CountingVision()

    for i in range(20):
        # Each iteration stands in for a fresh action with a fresh observer, so
        # the cache must not carry the previous iteration's AFTER state forward
        # as this iteration's BEFORE.
        from agent.perception.world_state_cache import reset_cache

        reset_cache()
        observer = FakeObserver(CHANGED)
        ctx = begin_observation(
            "browser_click",
            {"ref": f"@e{i}"},
            "t1",
            mode=VerificationMode.OBSERVE,
            observer=observer,
            ledger=ledger,
        )
        assert ctx is not None
        # A claim is supplied, and the DOM does change -> VERIFIED.
        from agent.verification import ExpectedTransition

        ctx.expected = ExpectedTransition(expect_dom_change=True)
        end_observation(
            ctx,
            "ok",
            success=True,
            observer=observer,
            policy=EscalationPolicy(),
            runner=vision,
            vision_available=True,
        )

    assert vision.calls == 0  # <-- ZERO vision calls across 20 normal clicks
    report = MetricsCollector()
    report.extend(ledger.entries())
    assert report.report().verified == 20
    assert report.report().vision_escalations == 0


def test_twenty_unknown_clicks_escalate_only_within_budget(tmp_path):
    """20 UNKNOWN with a 5-call budget -> exactly 5 vision calls."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    vision = CountingVision()
    policy = EscalationPolicy(min_risk=RiskLevel.MEDIUM, max_calls_per_session=5)

    used = 0
    for i in range(20):
        observer = FakeObserver(UNCHANGED)
        ctx = begin_observation(
            "browser_click",
            {"ref": f"@e{i}"},
            "t1",
            mode=VerificationMode.OBSERVE,
            observer=observer,
            ledger=ledger,
            expected=None,  # no claim -> UNKNOWN
        )
        assert ctx is not None
        ctx.calls_used = used
        end_observation(
            ctx,
            "ok",
            success=True,
            observer=observer,
            policy=policy,
            runner=vision,
            vision_available=True,
        )
        if ledger.entries()[-1].vision_escalated:
            used += 1

    assert vision.calls == 5  # <-- capped, not 20


def test_mixed_risk_levels_gate_escalation(tmp_path):
    """LOW never escalates; HIGH/CRITICAL do (when UNKNOWN)."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    vision = CountingVision()
    policy = EscalationPolicy(min_risk=RiskLevel.MEDIUM)

    for risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL):
        observer = FakeObserver(UNCHANGED)
        ctx = begin_observation(
            "browser_click",
            {"ref": "@e1"},
            "t1",
            mode=VerificationMode.OBSERVE,
            observer=observer,
            ledger=ledger,
            risk=risk,
            expected=None,
        )
        end_observation(
            ctx,
            "ok",
            success=True,
            observer=observer,
            policy=policy,
            runner=vision,
            vision_available=True,
        )

    assert vision.calls == 3  # LOW skipped, the other three escalated
    risks = {e.risk_level for e in ledger.entries()}
    assert risks == {"low", "medium", "high", "critical"}


# ── robustness: H2.0 must never break Hermes ──────────────────────────────
def test_browser_click_failure_is_still_recorded(tmp_path):
    """A failing action is observed, not swallowed or re-raised."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(UNCHANGED)

    ctx = begin_observation(
        "browser_click",
        {"ref": "@gone"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
    )
    evidence = end_observation(
        ctx,
        json.dumps({"error": "element not found"}),
        success=False,
        error="element not found",
        observer=observer,
    )

    assert evidence is not None
    entry = ledger.entries()[0]
    assert entry.tool_reported_success is False
    assert entry.error == "element not found"


def test_before_snapshot_failure_degrades_cleanly(tmp_path):
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(UNCHANGED, raise_on=1)  # first capture raises

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e1"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
    )

    assert ctx is not None
    assert ctx.before is None
    assert ctx.before_error is not None

    evidence = end_observation(ctx, "ok", success=True, observer=observer)

    assert evidence is not None
    assert evidence.outcome.value == "unknown"  # honest: we could not look
    assert ledger.entries()[0].observation_quality == EvidenceQuality.UNAVAILABLE.value


def test_after_snapshot_failure_degrades_cleanly(tmp_path):
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(CHANGED, raise_on=2)  # second capture raises

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e1"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
    )
    evidence = end_observation(ctx, "ok", success=True, observer=observer)

    assert evidence is not None
    assert evidence.outcome.value == "unknown"
    assert ledger.entries()[0].observation_quality == EvidenceQuality.UNAVAILABLE.value


def test_vision_unavailable_keeps_unknown_and_does_not_call(tmp_path):
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(UNCHANGED)
    vision = CountingVision()

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e1"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
        risk=RiskLevel.HIGH,
        expected=None,
    )
    end_observation(
        ctx,
        "ok",
        success=True,
        observer=observer,
        policy=EscalationPolicy(),
        runner=vision,
        vision_available=False,
    )

    assert vision.calls == 0
    assert ledger.entries()[0].final_verdict == "unknown"


def test_verifier_exception_does_not_propagate(tmp_path, monkeypatch):
    """If the verifier blows up, observation degrades — the tool call survives."""
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)
    observer = FakeObserver(CHANGED)

    import agent.verification.action_verifier as av

    def exploding_verify_action(**kwargs):  # noqa: ARG001
        raise RuntimeError("verifier exploded")

    monkeypatch.setattr(av, "verify_action", exploding_verify_action)

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e1"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
    )
    result = end_observation(ctx, "ok", success=True, observer=observer)

    # No exception escaped. The caller's trajectory is intact.
    assert result is None
    entry = ledger.entries()[0]
    assert entry.error is not None
    assert "verifier exploded" in entry.error


def test_ledger_failure_does_not_propagate(tmp_path):
    """If the ledger cannot write, the tool call still succeeds."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file")

    ledger = DecisionLedger(task_id="t1", directory=blocker)
    observer = FakeObserver(CHANGED)

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e1"},
        "t1",
        mode=VerificationMode.OBSERVE,
        observer=observer,
        ledger=ledger,
    )
    evidence = end_observation(ctx, "ok", success=True, observer=observer)

    assert evidence is not None  # observation still returned
    assert ledger.write_failures == 1  # failure is counted, not raised


def test_begin_observation_never_raises(monkeypatch):
    """Even a broken observer constructor must not raise."""

    class Boom:
        def __init__(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("cannot build observer")

    import agent.perception.browser_observer as bo

    monkeypatch.setattr(bo, "BrowserObserver", Boom)

    ctx = begin_observation(
        "browser_click", {"ref": "@e1"}, "t1", mode=VerificationMode.OBSERVE
    )

    # Either it degraded to None, or it produced a context with a before_error.
    if ctx is not None:
        assert ctx.before is None


def test_end_observation_with_none_ctx_is_a_noop():
    assert end_observation(None, "ok") is None


# ── metrics end-to-end ────────────────────────────────────────────────────
def test_metrics_over_a_realistic_observe_run(tmp_path):
    ledger = DecisionLedger(task_id="t1", directory=tmp_path)

    from agent.perception.world_state_cache import reset_cache
    from agent.verification import ExpectedTransition

    # 3 verified clicks
    for i in range(3):
        reset_cache()
        observer = FakeObserver(CHANGED)
        ctx = begin_observation(
            "browser_click",
            {"ref": f"@e{i}"},
            "t1",
            mode=VerificationMode.OBSERVE,
            observer=observer,
            ledger=ledger,
        )
        assert ctx is not None
        ctx.expected = ExpectedTransition(expect_dom_change=True)
        end_observation(ctx, "ok", success=True, observer=observer)

    # 2 unobservable clicks
    for i in range(2):
        observer = FakeObserver(UNCHANGED, raise_on=1)
        ctx = begin_observation(
            "browser_click",
            {"ref": f"@f{i}"},
            "t1",
            mode=VerificationMode.OBSERVE,
            observer=observer,
            ledger=ledger,
        )
        end_observation(ctx, "ok", success=True, observer=observer)

    collector = MetricsCollector()
    collector.extend(ledger.entries())
    report = collector.report()

    assert report.total_actions == 5
    assert report.verified == 3
    assert report.unobservable == 2
    assert report.observable_rate == round(3 / 5, 4)
    assert report.average_verification_latency >= 0.0
    json.dumps(report.to_dict())
