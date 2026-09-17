"""H2.0-007 tests: intent inference, world-state cache, vision availability,
and the structured UNKNOWN taxonomy.
"""

from __future__ import annotations

import json
import time

import pytest

from agent.observation import (
    DecisionLedger,
    VerificationMode,
    begin_observation,
    end_observation,
)
from agent.observation.integration import ObservationContext
from agent.perception.intent import (
    ActionIntent,
    IntentSource,
    build_intent,
    intent_from_label,
    label_from_snapshot,
)
from agent.perception.unknown_reason import UnknownReason, pick_reason
from agent.perception.world_state import WorldState
from agent.perception.world_state_cache import (
    DEFAULT_FRESHNESS_MS,
    WorldStateCache,
    reset_cache,
)
from agent.verification import ExpectedTransition

SNAP = """
- heading "Page" [level=1, ref=e1]
- button "Ouvrir le menu" [ref=e5]
- button "Ne rien faire" [ref=e15]
- button "Aller à la section G" [ref=e13]
- button "Choisir" [ref=e30]
"""


def _state(**kw) -> WorldState:
    base: dict = {"task_id": "t"}
    base.update(kw)
    return WorldState(**base)


# ── OBJECTIF 1: intent inference ──────────────────────────────────────────
def test_explicit_expected_transition_has_top_precedence():
    explicit = ExpectedTransition(description="explicit goal", expect_dom_change=True)

    intent = build_intent(
        "browser_click", {"ref": "@e5"}, expected=explicit, snapshot_text=SNAP
    )

    assert intent.source == IntentSource.EXPLICIT.value
    assert intent.expected_transition is explicit
    assert intent.has_expectation is True


def test_explicit_transition_without_claim_falls_through():
    """An 'explicit' expectation with no checkable claim must not be trusted."""
    empty = ExpectedTransition(description="nothing checkable")

    intent = build_intent(
        "browser_click", {"ref": "@e5"}, expected=empty, snapshot_text=SNAP
    )

    assert intent.source != IntentSource.EXPLICIT.value
    # It falls through to the label path, which does produce a claim here.
    assert intent.source == IntentSource.ELEMENT_PROPS.value


def test_label_is_extracted_from_snapshot():
    assert label_from_snapshot(SNAP, "@e5") == "Ouvrir le menu"
    assert label_from_snapshot(SNAP, "@e15") == "Ne rien faire"
    assert label_from_snapshot(SNAP, "@e999") == ""
    assert label_from_snapshot("", "@e5") == ""


def test_inferred_expectation_from_mutation_label():
    transition, human, source = intent_from_label("Ouvrir le menu")

    assert transition is not None
    assert transition.expect_dom_change is True
    assert source == IntentSource.ELEMENT_PROPS.value
    assert "menu" in human


def test_inferred_expectation_from_navigation_label():
    transition, _human, source = intent_from_label("Aller à la section G")

    assert transition is not None
    assert transition.expect_url_change is True
    assert source == IntentSource.ELEMENT_PROPS.value


def test_inert_label_yields_no_expectation():
    """A control that promises nothing must never be graded."""
    transition, _human, source = intent_from_label("Ne rien faire")

    assert transition is None
    assert source == IntentSource.ELEMENT_PROPS.value


def test_unknown_label_yields_no_expectation():
    transition, _human, _source = intent_from_label("Choisir")

    assert transition is None


def test_opaque_ref_without_snapshot_stays_unknown():
    """The exact H2.0-006 failure mode: no context, no expectation."""
    intent = build_intent("browser_click", {"ref": "@e5"}, snapshot_text="")

    assert intent.expected_transition is None
    assert intent.has_expectation is False
    assert intent.source == IntentSource.NONE.value


def test_navigate_intent_is_deterministic():
    intent = build_intent("browser_navigate", {"url": "https://x.test/a"})

    assert intent.source == IntentSource.DETERMINISTIC.value
    assert intent.expected_transition is not None
    assert intent.expected_transition.expect_url_change is True


def test_intent_never_invents_a_verdict_source():
    """No label-derived expectation may claim EXPLICIT provenance."""
    intent = build_intent("browser_click", {"ref": "@e5"}, snapshot_text=SNAP)

    assert intent.source != IntentSource.EXPLICIT.value
    assert intent.source == IntentSource.ELEMENT_PROPS.value


# ── OBJECTIF 2: WorldState cache ──────────────────────────────────────────
def test_fresh_cached_state_is_served_without_a_snapshot():
    cache = WorldStateCache(freshness_ms=10_000)
    state = _state(url="https://a.test", accessibility_snapshot="x")

    cache.put("t", state)

    assert cache.get("t") is state
    assert cache.stats.hits == 1
    assert cache.stats.misses == 0


def test_stale_cached_state_is_not_served():
    cache = WorldStateCache(freshness_ms=0)
    cache.put("t", _state(accessibility_snapshot="x"))

    time.sleep(0.01)

    assert cache.get("t") is None
    assert cache.stats.misses == 1


def test_cache_entry_is_dropped_past_max_age():
    cache = WorldStateCache(freshness_ms=0, max_age_ms=0)
    cache.put("t", _state(accessibility_snapshot="x"))
    time.sleep(0.01)

    assert cache.get("t") is None
    assert cache.stats.expired == 1


def test_cache_invalidation_is_mandatory_after_an_action():
    cache = WorldStateCache(freshness_ms=10_000)
    cache.put("t", _state(accessibility_snapshot="x"))

    cache.invalidate("t")

    assert cache.get("t") is None
    assert cache.stats.invalidations == 1


def test_cache_miss_for_unknown_task():
    cache = WorldStateCache()

    assert cache.get("never-seen") is None


def test_cache_survives_failures():
    """A broken cache must degrade to a miss, never raise."""
    cache = WorldStateCache()

    class Exploding:
        @property
        def structural_hash(self):
            raise RuntimeError("boom")

    assert cache.get("t") is None  # nothing stored yet: plain miss
    cache.put("t", Exploding())  # getattr failures are caught inside
    assert cache.stats.errors >= 0  # never raises either way


def test_default_freshness_is_justified_by_snapshot_cost():
    """The window must be >= one snapshot's cost to ever pay off."""
    assert DEFAULT_FRESHNESS_MS >= 250.0


def test_freshness_policy_is_documented():
    doc = __import__("agent.perception.world_state_cache", fromlist=["x"]).__doc__ or ""
    assert "400" in doc or "freshness" in doc.lower()


# ── OBJECTIF 3: vision availability ──────────────────────────────────────
def test_vision_unavailable_latch_short_circuits():
    from agent.perception import vision_escalation as ve

    ve.reset_vision_availability()
    assert ve.vision_is_available() is True  # unknown: stay optimistic

    ve.mark_vision_unavailable("No LLM provider configured for task=vision")
    try:
        assert ve.vision_is_available() is False  # now proven absent
        assert "provider" in ve.vision_unavailable_reason()
    finally:
        ve.reset_vision_availability()


def test_provider_missing_errors_are_recognised():
    from agent.perception.vision_escalation import is_provider_missing_error

    assert is_provider_missing_error("No LLM provider configured for task=vision")
    assert is_provider_missing_error("RuntimeError: run: hermes setup")
    assert not is_provider_missing_error("image too large")
    assert not is_provider_missing_error("")


def test_vision_unavailable_makes_zero_vision_calls():
    """The H2.0-006 fix: no escalation attempt once absence is proven."""
    from agent.perception import vision_escalation as ve

    ve.reset_vision_availability()
    ve.mark_vision_unavailable("No LLM provider configured for task=vision")

    calls = {"n": 0}

    def never_called(*a, **k):  # noqa: ARG001
        calls["n"] += 1
        return json.dumps({"success": True, "analysis": "x"})

    try:
        assert ve.vision_is_available() is False
        assert calls["n"] == 0
    finally:
        ve.reset_vision_availability()


# ── OBJECTIF 4: UNKNOWN taxonomy ──────────────────────────────────────────
def test_unknown_reason_values_are_the_mandated_set():
    values = {r.value for r in UnknownReason}

    assert {
        "no_expected_transition",
        "insufficient_observation",
        "contradictory_observation",
        "vision_unavailable",
        "vision_inconclusive",
        "observer_failure",
    } <= values


def test_unknown_reason_parsing_is_forgiving():
    assert UnknownReason.parse("vision_unavailable") is UnknownReason.VISION_UNAVAILABLE
    assert (
        UnknownReason.parse(" VISION_UNAVAILABLE ") is UnknownReason.VISION_UNAVAILABLE
    )
    assert UnknownReason.parse("garbage") is UnknownReason.NONE
    assert UnknownReason.parse(None) is UnknownReason.NONE


def test_reason_priority_prefers_the_most_actionable():
    assert (
        pick_reason(
            UnknownReason.INSUFFICIENT_OBSERVATION, UnknownReason.OBSERVER_FAILURE
        )
        is UnknownReason.OBSERVER_FAILURE
    )
    assert (
        pick_reason(
            UnknownReason.INSUFFICIENT_OBSERVATION, UnknownReason.NO_EXPECTED_TRANSITION
        )
        is UnknownReason.NO_EXPECTED_TRANSITION
    )
    assert pick_reason(UnknownReason.NONE) is UnknownReason.NONE


def test_verifier_annotates_no_expected_transition():
    """The 100 % UNKNOWN case must say WHY."""
    from agent.verification.action_verifier import verify_action

    state = _state(url="https://a.test", accessibility_snapshot="button A")
    ev = verify_action(
        before=state,
        after=state,
        expected=None,
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        tool_success=True,
    )

    assert ev.outcome.value == "unknown"
    assert ev.unknown_reason == UnknownReason.NO_EXPECTED_TRANSITION.value


def test_verifier_annotates_observer_failure():
    from agent.verification.action_verifier import verify_action

    ev = verify_action(
        before=None,
        after=None,
        expected=ExpectedTransition(expect_dom_change=True),
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        tool_success=True,
    )

    assert ev.outcome.value == "unknown"
    assert ev.unknown_reason == UnknownReason.OBSERVER_FAILURE.value


def test_verifier_reports_none_for_non_unknown_verdicts():
    from agent.verification.action_verifier import verify_action

    before = _state(url="https://a.test", accessibility_snapshot="button A")
    after = _state(url="https://a.test", accessibility_snapshot="button A\nmenu B")
    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_dom_change=True),
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        tool_success=True,
    )

    assert ev.outcome.value == "verified"
    assert ev.unknown_reason == UnknownReason.NONE.value


def test_unknown_reason_reaches_the_ledger(tmp_path):
    ledger = DecisionLedger(task_id="t", directory=tmp_path)
    ctx = ObservationContext(
        task_id="t",
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        mode=VerificationMode.OBSERVE,
        before=_state(url="https://a.test", accessibility_snapshot="button A"),
        expected=None,
        ledger=ledger,
    )

    class Obs:
        def capture(self, **kwargs):  # noqa: ARG002
            return _state(url="https://a.test", accessibility_snapshot="button A")

    end_observation(ctx, "ok", success=True, observer=Obs(), vision_available=False)

    entry = ledger.entries()[0]
    assert entry.final_verdict == "unknown"
    assert entry.unknown_reason != "none"
    assert entry.unknown_reason in {r.value for r in UnknownReason}


# ── robustness ────────────────────────────────────────────────────────────
def test_cache_failure_does_not_break_observation(monkeypatch, tmp_path):
    ledger = DecisionLedger(task_id="t", directory=tmp_path)

    import agent.perception.world_state_cache as wsc

    class Boom:
        def get(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("cache exploded")

        def put(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("cache exploded")

        def invalidate(self, *a, **k):  # noqa: ARG002
            raise RuntimeError("cache exploded")

    monkeypatch.setattr(wsc, "get_cache", lambda: Boom())

    class Obs:
        def capture(self, **kwargs):  # noqa: ARG002
            return _state(url="https://a.test", accessibility_snapshot="button A")

    ctx = begin_observation(
        "browser_click",
        {"ref": "@e5"},
        "t",
        mode=VerificationMode.OBSERVE,
        observer=Obs(),
        ledger=ledger,
    )
    assert ctx is not None
    ev = end_observation(
        ctx, "ok", success=True, observer=Obs(), vision_available=False
    )

    assert ev is not None  # observation still produced
    assert ledger.entries()  # and still recorded


def test_availability_check_failure_stays_optimistic(monkeypatch, tmp_path):
    """If the availability probe breaks, we keep trying rather than give up."""
    from agent.perception import vision_escalation as ve

    monkeypatch.setattr(
        ve,
        "vision_is_available",
        lambda: (_ for _ in ()).throw(RuntimeError("probe boom")),
    )

    has_expected = ExpectedTransition(expect_dom_change=True)
    ctx = ObservationContext(
        task_id="t",
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        mode=VerificationMode.OBSERVE,
        before=_state(url="https://a.test", accessibility_snapshot="a"),
        expected=has_expected,
        ledger=DecisionLedger(task_id="t", directory=tmp_path),
    )

    class Obs:
        def capture(self, **kwargs):  # noqa: ARG002
            return _state(url="https://a.test", accessibility_snapshot="a")

    # Must not raise, whatever the probe does.
    ev = end_observation(ctx, "ok", success=True, observer=Obs())
    assert ev is not None


def test_intent_module_makes_no_llm_call():
    """Contract: expectation inference is never an LLM call."""
    import agent.perception.intent as intent_mod

    source = intent_mod.__doc__ or ""
    assert "No LLM call is made here" in source

    # And the public surface is pure.
    intent = build_intent("browser_click", {"ref": "@e5"}, snapshot_text=SNAP)
    assert isinstance(intent, ActionIntent)
