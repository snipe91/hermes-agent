"""Tests for the Hermes 2.0 per-action verifier.

Covers the eight mandated scenarios:
    action + expected change        -> VERIFIED
    action with no change           -> UNKNOWN
    unexpected change               -> FAILED
    navigation to the wrong page    -> FAILED
    overlay appeared                -> FAILED (observable) / UNKNOWN (blind)
    success=True, goal undemonstrated -> UNKNOWN
    identical before/after          -> UNKNOWN
    verifier cannot determine       -> UNKNOWN
"""

from __future__ import annotations

import json

from agent.perception.world_state import WorldState
from agent.verification import (
    ActionVerifier,
    ExpectedTransition,
    Outcome,
    infer_expected_transition,
    verify_action,
)


def _state(**kwargs) -> WorldState:
    base: dict = {"task_id": "test"}
    base.update(kwargs)
    return WorldState(**base)


# ── 1. action + expected change -> VERIFIED ───────────────────────────────
def test_expected_url_change_is_verified():
    before = _state(
        url="https://app.test/login", accessibility_snapshot="button Connexion"
    )
    after = _state(
        url="https://app.test/dashboard",
        accessibility_snapshot="heading Tableau de bord",
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(
            description="se connecter",
            expect_url_change=True,
            expect_url_contains="dashboard",
        ),
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        tool_success=True,
    )

    assert ev.outcome is Outcome.VERIFIED
    assert ev.verified is True
    assert ev.would_retry is False


def test_expected_dom_change_is_verified():
    before = _state(url="https://app.test/x", accessibility_snapshot="button Ouvrir")
    after = _state(
        url="https://app.test/x",
        accessibility_snapshot="button Ouvrir\nmenu Paramètres",
        element_count=2,
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_dom_change=True),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.VERIFIED


# ── 2. action with no change -> UNKNOWN ───────────────────────────────────
def test_action_without_change_and_no_claim_is_unknown():
    """No observable change and nothing claimed: we cannot tell, so UNKNOWN."""
    same = _state(url="https://app.test/a", accessibility_snapshot="button OK")
    other = _state(url="https://app.test/a", accessibility_snapshot="button OK")

    ev = verify_action(
        before=same,
        after=other,
        expected=None,
        tool_name="browser_click",
        tool_success=True,
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert ev.failed is False
    assert ev.would_retry is False
    assert any("no expectation" in r for r in ev.reasons)
    assert (
        ev.metadata["note"]
        == "tool reported success but the objective is not demonstrated"
    )


# ── 3. unexpected change -> FAILED ────────────────────────────────────────
def test_unexpected_url_change_is_failed():
    before = _state(url="https://app.test/checkout")
    after = _state(url="https://app.test/error")

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(
            description="rester sur le panier", expect_url_change=False
        ),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.FAILED
    assert ev.failed is True
    assert ev.would_retry is True
    assert any("unexpectedly" in r for r in ev.reasons)


def test_unexpected_dom_change_is_failed():
    before = _state(url="https://app.test/x", accessibility_snapshot="button OK")
    after = _state(
        url="https://app.test/x",
        accessibility_snapshot="button OK\nmenu Autre chose",
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_dom_change=False),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.FAILED


# ── 4. navigation to the wrong page -> FAILED ─────────────────────────────
def test_navigation_to_wrong_page_is_failed():
    before = _state(url="https://app.test/home")
    after = _state(url="https://app.test/404")

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(
            description="ouvrir le programme",
            expect_url_change=True,
            expect_url_contains="programme",
        ),
        tool_name="browser_click",
        tool_success=True,  # the click "worked", the outcome did not
    )

    assert ev.outcome is Outcome.FAILED
    assert any("does not contain" in r for r in ev.reasons)


def test_forbidden_url_fragment_is_failed():
    before = _state(url="https://app.test/home")
    after = _state(url="https://app.test/login?error=session")

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_missing="login"),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.FAILED


# ── 5. overlay appeared -> FAILED (observable) / UNKNOWN (blind) ──────────
def test_overlay_appearance_is_failed_when_observable():
    before = _state(
        url="https://app.test/x",
        accessibility_snapshot="button OK",
        metadata={"has_supervisor_state": True},
    )
    after = _state(
        url="https://app.test/x",
        accessibility_snapshot="button OK",
        overlays=({"type": "modal", "label": "Tutoriel"},),
        metadata={"has_supervisor_state": True},
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_change=False),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.FAILED
    assert any("obstacle appeared" in r for r in ev.reasons)
    assert ev.metadata["obstacles_observable"] is True


def test_overlay_claim_not_observable_does_not_prove_success():
    """With no supervisor state the obstacle claim is vacuous; we must not
    silently treat 'could not look' as 'clean'."""
    before = _state(url="https://app.test/x", accessibility_snapshot="a")
    after = _state(url="https://app.test/x", accessibility_snapshot="a\nb")

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_dom_change=True, expect_no_obstacles=True),
        tool_name="browser_click",
    )

    # The DOM claim is satisfied; the obstacle check was simply not observable.
    assert ev.metadata["obstacles_observable"] is False
    assert ev.outcome is Outcome.VERIFIED
    assert any("obstacles not observable" in r for r in ev.reasons)


# ── 6. success=True but goal undemonstrated -> UNKNOWN ────────────────────
def test_tool_reports_success_but_objective_undemonstrated():
    before = _state(url="https://app.test/a", accessibility_snapshot="button Save")
    after = _state(url="https://app.test/a", accessibility_snapshot="button Save")

    ev = verify_action(
        before=before,
        after=after,
        expected=None,  # nobody stated the goal
        tool_name="browser_click",
        tool_args={"ref": "@e9"},
        tool_success=True,
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert ev.tool_success is True
    assert ev.metadata["tool_success_is_proof"] is False


def test_success_true_still_fails_when_claims_violated():
    """Contradictory evidence beats the tool's self-report."""
    before = _state(url="https://app.test/panier")
    after = _state(url="https://app.test/erreur-500")

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_contains="confirmation"),
        tool_name="browser_click",
        tool_success=True,
    )

    assert ev.outcome is Outcome.FAILED


# ── 7. identical before/after -> UNKNOWN (no claim) / FAILED (claim unmet) ──
def test_identical_states_without_claim_yield_unknown():
    """Nothing was claimed and nothing changed: we genuinely cannot tell.

    This is the honest UNKNOWN. It must not be reported as a failure, because
    an idempotent action legitimately produces no observable change.
    """
    state = _state(
        url="https://app.test/x", accessibility_snapshot="button OK", element_count=1
    )

    ev = verify_action(
        before=state,
        after=state,
        expected=None,
        tool_name="browser_click",
        tool_success=True,
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert ev.failed is False
    assert ev.would_retry is False


def test_identical_states_with_unmet_dom_claim_is_failed():
    """Distinct from the above: here the caller *asserted* a change was required.

    An explicit claim that is demonstrably not met is a proven failure, not an
    unknown — the evidence is contradictory, not absent.
    """
    state = _state(
        url="https://app.test/x", accessibility_snapshot="button OK", element_count=1
    )

    ev = verify_action(
        before=state,
        after=state,
        expected=ExpectedTransition(expect_dom_change=True),
        tool_name="browser_click",
        tool_success=True,
    )

    assert ev.outcome is Outcome.FAILED
    assert any("unchanged" in r for r in ev.reasons)


# ── 8. verifier cannot determine -> UNKNOWN ───────────────────────────────
def test_missing_observation_is_unknown():
    ev = verify_action(
        before=None,
        after=_state(url="https://app.test/x"),
        expected=ExpectedTransition(expect_url_change=True),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert any("missing observation" in r for r in ev.reasons)


def test_failed_observation_is_unknown_not_failed():
    after = _state(metadata={"observation_error": "browser unavailable"})

    ev = verify_action(
        before=_state(url="https://app.test/x"),
        after=after,
        expected=ExpectedTransition(expect_url_change=True),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert ev.failed is False
    assert any("observation failed" in r for r in ev.reasons)


def test_empty_expectation_is_unknown():
    before = _state(url="https://app.test/a", accessibility_snapshot="a")
    after = _state(url="https://app.test/b", accessibility_snapshot="b")

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(description="cliquer sur Enregistrer"),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert any("no checkable claim" in r for r in ev.reasons)


def test_loading_with_pending_navigation_is_unknown():
    """A URL that has not changed yet, on a page still loading, is not a failure.

    Note: `loading` is normally inferred by BrowserObserver from snapshot text;
    here it is set explicitly because these WorldStates are built by hand.
    """
    before = _state(
        url="https://app.test/a", accessibility_snapshot="button Go", loading=False
    )
    after = _state(
        url="https://app.test/a",
        accessibility_snapshot="Loading… button Go",
        loading=True,
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_change=True),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.UNKNOWN
    assert ev.failed is False
    assert any("still loading" in r for r in ev.reasons)


def test_loading_observed_by_observer_is_detected_from_text():
    """The observer's textual loading hint feeds the same code path."""
    from agent.perception import BrowserObserver

    observer = BrowserObserver(task_id="t1")
    before = observer._build_state({
        "success": True,
        "snapshot": "Page URL: https://app.test/a\nbutton Go",
        "element_count": 1,
    })
    after = observer._build_state({
        "success": True,
        "snapshot": "Page URL: https://app.test/a\nLoading… please wait",
        "element_count": 1,
    })

    assert before.loading is False
    assert after.loading is True

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_change=True),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.UNKNOWN


# ── expectation inference ─────────────────────────────────────────────────
def test_infer_navigation_expectation():
    transition = infer_expected_transition(
        "browser_navigate", {"url": "https://fitclair.com/dashboard"}
    )

    assert transition is not None
    assert transition.expect_url_change is True
    assert transition.expect_url_contains == "fitclair.com/dashboard"


def test_infer_returns_none_for_click():
    """A click ref carries no machine-readable goal -> must be None, not a guess."""
    assert infer_expected_transition("browser_click", {"ref": "@e5"}) is None


def test_infer_navigation_without_url_returns_none():
    assert infer_expected_transition("browser_navigate", {}) is None


# ── ActionVerifier plumbing ───────────────────────────────────────────────
def test_verifier_around_context_manager_does_not_call_tools():
    """The verifier must never invoke a browser tool itself."""
    calls: list[str] = []

    class FakeObserver:
        def capture(self, **kwargs):
            calls.append("observe")
            return _state(url="https://app.test/x", accessibility_snapshot="button OK")

    verifier = ActionVerifier(task_id="t1", observer=FakeObserver())  # type: ignore[arg-type]

    with verifier.around(
        "browser_click",
        {"ref": "@e5"},
        expected=ExpectedTransition(expect_url_change=False),
    ) as done:
        # The caller owns execution; we deliberately do NOT call browser_click.
        evidence = done(True)

    assert calls == ["observe", "observe"]  # before + after only
    assert evidence.outcome is Outcome.VERIFIED
    assert evidence.tool_name == "browser_click"


def test_verifier_accepts_precaptured_after_state():
    class FakeObserver:
        def capture(self, **kwargs):
            raise AssertionError("must not observe when after= is supplied")

    verifier = ActionVerifier(task_id="t1", observer=FakeObserver())  # type: ignore[arg-type]

    evidence = verifier.verify_after(
        before=_state(url="https://a.test"),
        after=_state(url="https://b.test"),
        tool_name="browser_navigate",
        expected=ExpectedTransition(expect_url_change=True),
    )

    assert evidence.outcome is Outcome.VERIFIED


def test_evidence_is_json_serialisable_end_to_end():
    before = _state(url="https://app.test/a", accessibility_snapshot="button OK")
    after = _state(
        url="https://app.test/b",
        accessibility_snapshot="button OK\nmenu Next",
        element_count=3,
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_change=True, expect_dom_change=True),
        tool_name="browser_click",
        tool_args={"ref": "@e5"},
        tool_success=True,
    )

    json.dumps(ev.to_dict())
    json.dumps(ev.summary())
    assert ev.outcome is Outcome.VERIFIED
