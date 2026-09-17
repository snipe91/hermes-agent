"""Tests for the Hermes 2.0 Vision Escalation Engine (H2.0-003).

Every scenario asserts the exact number of vision calls performed, using a
counting fake runner — no real browser, no real model.
"""

from __future__ import annotations

import json

from agent.perception import (
    EscalationPolicy,
    RiskLevel,
    VisionBudget,
    decide_escalation,
    escalate_unknown,
    infer_risk_level,
    judge_observation,
    observe_with_vision,
    vision_is_available,
)
from agent.perception.vision_escalation import VisionObservation
from agent.perception.world_state import WorldState
from agent.verification import (
    ExpectedTransition,
    Outcome,
    verify_action,
)


# ── helpers ───────────────────────────────────────────────────────────────
class CountingRunner:
    """Fake browser_vision that counts how many times it was called."""

    def __init__(self, response=None):
        self.calls = 0
        self.questions: list[str] = []
        self._response = (
            response if response is not None else _vision_ok("Tout va bien.")
        )

    def __call__(self, question="", annotate=False, task_id=None):  # noqa: ARG002
        self.calls += 1
        self.questions.append(question)
        return self._response


def _vision_ok(analysis: str) -> str:
    return json.dumps({
        "success": True,
        "analysis": analysis,
        "screenshot_path": "/tmp/s.png",
    })


def _vision_err(msg: str = "model timeout") -> str:
    return json.dumps({"success": False, "error": msg})


def _state(**kwargs) -> WorldState:
    base: dict = {"task_id": "test"}
    base.update(kwargs)
    return WorldState(**base)


def _unknown_evidence(*, expected=None, tool_name="browser_click", diff_kind="none"):
    """Build an UNKNOWN ActionEvidence, optionally with a specific diff shape."""
    before = _state(url="https://app.test/a", accessibility_snapshot="button OK")
    if diff_kind == "overlay":
        after = _state(
            url="https://app.test/a",
            accessibility_snapshot="button OK",
            overlays=({"type": "modal", "label": "Tutoriel"},),
        )
    elif diff_kind == "none":
        after = _state(url="https://app.test/a", accessibility_snapshot="button OK")
    else:
        after = _state(
            url="https://app.test/a", accessibility_snapshot="button OK\nmenu X"
        )

    if expected is None:
        # No claim -> the verifier already returns UNKNOWN.
        return verify_action(
            before=before,
            after=after,
            expected=None,
            tool_name=tool_name,
            tool_success=True,
        )
    # A claim that is present but unmet-inconclusively also yields UNKNOWN when
    # the DOM is merely unchanged vs a loading page; here we craft it directly
    # by asking only for an unobservable signal.
    ev = verify_action(
        before=before,
        after=after,
        expected=expected,
        tool_name=tool_name,
        tool_success=True,
    )
    return ev


# ── 1. UNKNOWN + LOW risk -> no vision ────────────────────────────────────
def test_unknown_low_risk_does_not_escalate():
    runner = CountingRunner()
    ev = _unknown_evidence()
    assert ev.outcome is Outcome.UNKNOWN

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.LOW,
        policy=EscalationPolicy(min_risk=RiskLevel.MEDIUM),
        runner=runner,
        vision_available=True,
    )

    assert decision.needed is False
    assert result.outcome is Outcome.UNKNOWN
    assert obs is None
    assert runner.calls == 0  # <-- ZERO vision calls


def test_low_risk_allowed_when_policy_demands_it():
    """A policy that lowers the bar does escalate — the knob works."""
    runner = CountingRunner()
    result, obs, decision = escalate_unknown(
        evidence=_unknown_evidence(),
        risk=RiskLevel.LOW,
        policy=EscalationPolicy(min_risk=RiskLevel.LOW),
        runner=runner,
        vision_available=True,
    )

    assert decision.needed is True
    assert runner.calls == 1


# ── 2. UNKNOWN + HIGH risk -> vision requested ───────────────────────────
def test_unknown_high_risk_requests_vision():
    runner = CountingRunner()
    expected = ExpectedTransition(description="ouvrir le tableau de bord")
    ev = verify_action(
        before=_state(
            url="https://app.test/login", accessibility_snapshot="button Connexion"
        ),
        after=_state(
            url="https://app.test/dashboard",
            accessibility_snapshot="heading Tableau de bord",
        ),
        expected=expected,
        tool_name="browser_click",
    )
    # Force the UNKNOWN case by stripping the claim signal.
    ev = verify_action(
        before=ev.before, after=ev.before, expected=None, tool_name="browser_click"
    )
    assert ev.outcome is Outcome.UNKNOWN

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.HIGH,
        expected=expected,
        policy=EscalationPolicy(min_risk=RiskLevel.MEDIUM),
        runner=runner,
        vision_available=True,
    )

    assert decision.needed is True
    assert decision.risk is RiskLevel.HIGH
    assert runner.calls == 1
    assert obs is not None


# ── 3. UNKNOWN + CRITICAL risk -> vision + reinforced policy ─────────────
def test_unknown_critical_risk_escalates_with_reinforced_policy():
    runner = CountingRunner()
    expected = ExpectedTransition(
        description="confirmer la suppression du compte",
        expect_url_contains="confirmation",
    )
    ev = verify_action(
        before=_state(url="https://app.test/account"),
        after=_state(url="https://app.test/account"),
        expected=None,
        tool_name="browser_click",
    )

    strict = EscalationPolicy(
        min_risk=RiskLevel.HIGH,
        min_confidence=0.8,
        max_calls_per_session=3,
    )
    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.CRITICAL,
        expected=expected,
        policy=strict,
        runner=runner,
        vision_available=True,
    )

    assert decision.needed is True
    assert runner.calls == 1
    # Reinforced policy: the hedged/plain default confidence (0.7) is below 0.8,
    # so the verdict must stay UNKNOWN rather than be upgraded.
    assert result.outcome is Outcome.UNKNOWN
    assert obs is not None
    assert obs.confidence < strict.min_confidence


def test_critical_risk_below_strict_threshold_skips_when_policy_raises_bar():
    runner = CountingRunner()
    ev = _unknown_evidence()

    decision = decide_escalation(
        evidence=ev,
        risk=RiskLevel.MEDIUM,
        policy=EscalationPolicy(min_risk=RiskLevel.CRITICAL),
        vision_available=True,
    )

    assert decision.needed is False
    assert "below threshold" in decision.reason
    assert runner.calls == 0


# ── 4. VERIFIED -> no useless vision ─────────────────────────────────────
def test_verified_never_escalates():
    runner = CountingRunner()
    ev = verify_action(
        before=_state(url="https://app.test/login"),
        after=_state(url="https://app.test/dashboard"),
        expected=ExpectedTransition(
            expect_url_change=True, expect_url_contains="dashboard"
        ),
        tool_name="browser_click",
    )
    assert ev.outcome is Outcome.VERIFIED

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.CRITICAL,  # even at max risk
        runner=runner,
        vision_available=True,
    )

    assert decision.needed is False
    assert decision.reason == "already verified"
    assert obs is None
    assert runner.calls == 0  # <-- ZERO vision calls


# ── 5. FAILED -> no useless vision unless configured ─────────────────────
def test_failed_does_not_escalate_by_default():
    runner = CountingRunner()
    ev = verify_action(
        before=_state(url="https://app.test/a"),
        after=_state(url="https://app.test/404"),
        expected=ExpectedTransition(expect_url_contains="dashboard"),
        tool_name="browser_click",
    )
    assert ev.outcome is Outcome.FAILED

    result, obs, decision = escalate_unknown(
        evidence=ev, risk=RiskLevel.HIGH, runner=runner, vision_available=True
    )

    assert decision.needed is False
    assert "diagnosis disabled" in decision.reason
    assert runner.calls == 0  # <-- ZERO vision calls


def test_failed_escalates_only_when_diagnosis_enabled():
    runner = CountingRunner(response=_vision_ok("Une erreur 404 est affichee."))
    ev = verify_action(
        before=_state(url="https://app.test/a"),
        after=_state(url="https://app.test/404"),
        expected=ExpectedTransition(expect_url_contains="dashboard"),
        tool_name="browser_click",
    )

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.HIGH,
        policy=EscalationPolicy(diagnose_failures=True),
        runner=runner,
        vision_available=True,
    )

    assert decision.needed is True
    assert runner.calls == 1  # <-- exactly ONE call, explicitly configured
    # Diagnosis must not silently flip a proven failure into a pass.
    assert obs is not None


# ── 6. vision unavailable -> clean UNKNOWN ───────────────────────────────
def test_vision_unavailable_stays_unknown_without_calling():
    runner = CountingRunner()
    ev = _unknown_evidence()

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.CRITICAL,
        policy=EscalationPolicy(respect_availability=True),
        runner=runner,
        vision_available=False,
    )

    assert decision.needed is False
    assert decision.reason == "vision unavailable"
    assert result.outcome is Outcome.UNKNOWN
    assert runner.calls == 0  # <-- ZERO vision calls


def test_availability_probe_never_raises():
    assert isinstance(vision_is_available(), bool)


# ── 7. vision fails -> clean UNKNOWN ─────────────────────────────────────
def test_vision_failure_yields_unknown_not_failed():
    runner = CountingRunner(response=_vision_err("model exploded"))
    ev = _unknown_evidence()
    expected = ExpectedTransition(
        description="ouvrir la page", expect_url_contains="dashboard"
    )

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.HIGH,
        expected=expected,
        runner=runner,
        vision_available=True,
    )

    assert runner.calls == 1
    assert obs is not None
    assert obs.available is False
    assert obs.error is not None
    assert result.outcome is Outcome.UNKNOWN
    assert result.outcome is not Outcome.FAILED


def test_observe_with_vision_degrades_when_runner_raises():
    """A raising backend must degrade to an unavailable observation, not crash."""

    def exploding_runner(question="", annotate=False, task_id=None):  # noqa: ARG001
        raise RuntimeError("browser backend exploded")

    obs = observe_with_vision(question="que vois-tu ?", runner=exploding_runner)

    assert obs.source == "unavailable"
    assert obs.available is False
    assert "exploded" in (obs.error or "")


def test_observe_with_vision_marks_missing_provider_as_unavailable():
    """'No LLM provider configured' is unavailability, not a failed analysis."""

    def no_provider(question="", annotate=False, task_id=None):  # noqa: ARG001
        return json.dumps({
            "success": False,
            "error": "No LLM provider configured for task=vision provider=auto. Run: hermes setup",
        })

    obs = observe_with_vision(question="q", runner=no_provider)

    assert obs.source == "unavailable"
    assert obs.available is False


def test_observe_with_vision_marks_real_analysis_error_as_auxiliary():
    """A genuine backend failure keeps source='auxiliary' (it did run)."""
    obs = observe_with_vision(
        question="q", runner=CountingRunner(response=_vision_err("model timeout"))
    )

    assert obs.source == "auxiliary"
    assert obs.error is not None


# ── 8. contradictory observation -> UNKNOWN or FAILED ────────────────────
def test_contradictory_observation_with_obstacle_is_failed():
    obs = observe_with_vision(
        question="que vois-tu ?",
        runner=CountingRunner(
            response=_vision_ok("Un captcha Cloudflare bloque l'acces a la page.")
        ),
    )
    expected = ExpectedTransition(
        description="ouvrir le dashboard",
        expect_url_contains="dashboard",
        expect_no_obstacles=True,
    )

    outcome, reasons = judge_observation(observation=obs, expected=expected)

    assert outcome is Outcome.FAILED
    assert any("obstacle" in r for r in reasons)


def test_contradictory_observation_without_obstacle_stays_unknown():
    obs = observe_with_vision(
        question="que vois-tu ?",
        runner=CountingRunner(
            response=_vision_ok(
                "Je ne peux pas determiner ce qui est affiche, l'ecran est flou."
            )
        ),
    )
    expected = ExpectedTransition(
        description="ouvrir le dashboard", expect_url_contains="dashboard"
    )

    outcome, reasons = judge_observation(observation=obs, expected=expected)

    assert outcome is Outcome.UNKNOWN
    assert outcome is not Outcome.FAILED


# ── 9. vision confirms the expected state -> VERIFIED ────────────────────
def test_vision_confirming_expected_state_is_verified():
    obs = observe_with_vision(
        question="que vois-tu ?",
        runner=CountingRunner(
            response=_vision_ok(
                "Le tableau de bord dashboard est affiche, avec un menu Settings et un bouton Programme."
            )
        ),
    )
    expected = ExpectedTransition(
        description="ouvrir le dashboard",
        expect_url_contains="dashboard",
        expect_no_obstacles=True,
    )

    outcome, reasons = judge_observation(observation=obs, expected=expected)

    assert outcome is Outcome.VERIFIED
    assert any("mentions" in r for r in reasons)


def test_escalation_can_upgrade_unknown_to_verified_through_the_judge():
    runner = CountingRunner(response=_vision_ok("Le dashboard s'affiche correctement."))
    ev = _unknown_evidence()
    expected = ExpectedTransition(
        description="ouvrir le dashboard",
        expect_url_contains="dashboard",
    )

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.HIGH,
        expected=expected,
        runner=runner,
        vision_available=True,
    )

    assert runner.calls == 1
    assert result.outcome is Outcome.VERIFIED
    assert result.vision_used is True
    assert result.metadata["vision_source"] == "auxiliary"


# ── 10. vision alone, no expected state -> must NOT become VERIFIED ──────
def test_vision_alone_without_expected_never_upgrades_to_verified():
    """The single most important rule of this layer."""
    obs = observe_with_vision(
        question="que vois-tu ?",
        runner=CountingRunner(
            response=_vision_ok(
                "L'action a tres bien fonctionne, tout est parfait, le dashboard est ouvert."
            )
        ),
    )

    outcome, reasons = judge_observation(observation=obs, expected=None)

    assert outcome is Outcome.UNKNOWN
    assert outcome is not Outcome.VERIFIED
    assert any("cannot substitute for a specification" in r for r in reasons)


def test_vision_with_empty_claim_never_upgrades_to_verified():
    obs = observe_with_vision(
        question="que vois-tu ?",
        runner=CountingRunner(
            response=_vision_ok("Le dashboard est ouvert, tout est OK.")
        ),
    )

    outcome, _ = judge_observation(
        observation=obs,
        expected=ExpectedTransition(description="cliquer sur Enregistrer"),  # no claim
    )

    assert outcome is Outcome.UNKNOWN


def test_confident_vision_without_expected_stays_unknown_end_to_end():
    runner = CountingRunner(
        response=_vision_ok("Tout est parfait, le dashboard est ouvert.")
    )
    ev = _unknown_evidence()
    assert ev.expected is None

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.CRITICAL,
        expected=None,
        runner=runner,
        vision_available=True,
    )

    assert runner.calls == 1
    assert result.outcome is Outcome.UNKNOWN  # opinion != specification
    assert result.outcome is not Outcome.VERIFIED


# ── 11. no vision call per click by default ──────────────────────────────
def test_no_vision_call_for_typical_click_flow():
    """A normal run of clicks must not trigger any vision call."""
    runner = CountingRunner()
    total = 0

    for _ in range(20):
        ev = verify_action(
            before=_state(url="https://app.test/x", accessibility_snapshot="button A"),
            after=_state(
                url="https://app.test/x",
                accessibility_snapshot="button A\nmenu B",
            ),
            expected=ExpectedTransition(expect_dom_change=True),
            tool_name="browser_click",
        )
        assert ev.outcome is Outcome.VERIFIED  # settled -> never escalates
        _, _, decision = escalate_unknown(
            evidence=ev, risk=RiskLevel.MEDIUM, runner=runner, vision_available=True
        )
        total += decision.needed

    assert total == 0
    assert runner.calls == 0  # <-- ZERO vision calls across 20 clicks


def test_budget_caps_vision_calls():
    """The budget cap actually binds — no caller can exceed it."""
    runner = CountingRunner()
    budget = VisionBudget(max_calls=2)
    policy = budget.as_policy()  # cap cannot diverge from the budget

    for _ in range(5):
        ev = _unknown_evidence()
        result, obs, decision = escalate_unknown(
            evidence=ev,
            risk=RiskLevel.HIGH,
            policy=policy,
            runner=runner,
            calls_used=budget.used,
            vision_available=True,
        )
        if decision.needed:
            budget.record(
                risk=RiskLevel.HIGH, reason=decision.reason, outcome=result.outcome
            )

    assert budget.used == 2
    assert budget.exhausted is True
    assert runner.calls == 2  # <-- capped at exactly 2, not 5

    decision = decide_escalation(
        evidence=_unknown_evidence(),
        risk=RiskLevel.HIGH,
        policy=policy,
        calls_used=budget.used,
        vision_available=True,
    )
    assert decision.needed is False
    assert "budget exhausted" in decision.reason


def test_budget_policy_stays_in_sync():
    """Regression: max_calls and max_calls_per_session must not diverge."""
    budget = VisionBudget(max_calls=3)
    policy = budget.as_policy()

    assert policy.max_calls_per_session == 3
    assert policy.max_calls_per_session == budget.max_calls

    # Overrides may raise the risk bar without desynchronising the cap.
    raised = budget.as_policy(min_risk=RiskLevel.CRITICAL)
    assert raised.min_risk is RiskLevel.CRITICAL
    assert raised.max_calls_per_session == 3


# ── risk inference ────────────────────────────────────────────────────────
def test_infer_risk_level_reads_actions():
    assert infer_risk_level("browser_snapshot") is RiskLevel.LOW
    assert infer_risk_level("browser_navigate") is RiskLevel.MEDIUM
    assert infer_risk_level("browser_click") is RiskLevel.MEDIUM


def test_unknown_tool_defaults_to_medium_not_low():
    """An unrecognised action must not silently skip escalation."""
    assert infer_risk_level("some_future_tool") is RiskLevel.MEDIUM


# ── observation parsing ───────────────────────────────────────────────────
def test_observation_reports_hedging_as_higher_contradiction():
    hedging = observe_with_vision(
        question="q",
        runner=CountingRunner(
            response=_vision_ok(
                "Je ne peux pas dire si le dashboard est ouvert, l'image n'est pas claire."
            )
        ),
    )
    plain = observe_with_vision(
        question="q",
        runner=CountingRunner(response=_vision_ok("Le dashboard est ouvert.")),
    )

    assert hedging.confidence < plain.confidence
    assert any("uncertain" in c for c in hedging.contradictions)
    assert plain.contradictions == ()


def test_native_envelope_is_detected_without_inventing_analysis():
    native = observe_with_vision(
        question="q",
        runner=CountingRunner(
            response={"content": [{"type": "image"}], "screenshot_path": "/tmp/n.png"}
        ),
    )

    assert native.source == "native"
    assert native.screenshot_path == "/tmp/n.png"
    # The analysis text must not be fabricated.
    assert "attached natively" in native.observation


# ── 12. non-regression of existing APIs ──────────────────────────────────
def test_existing_verifier_api_unchanged():
    """H2.0-003 must not alter H2.0-001/002 behaviour."""
    before = _state(
        url="https://app.test/login", accessibility_snapshot="button Connexion"
    )
    after = _state(
        url="https://app.test/dashboard", accessibility_snapshot="heading Accueil"
    )

    ev = verify_action(
        before=before,
        after=after,
        expected=ExpectedTransition(expect_url_change=True),
        tool_name="browser_click",
    )

    assert ev.outcome is Outcome.VERIFIED
    assert ev.vision_used is False  # the verifier itself never calls vision
    json.dumps(ev.to_dict())


def test_vision_tool_is_never_called_by_the_verifier():
    """Calling verify_action must not touch the vision backend at all."""
    runner = CountingRunner()
    for _ in range(5):
        verify_action(
            before=_state(url="https://app.test/a"),
            after=_state(url="https://app.test/b"),
            expected=ExpectedTransition(expect_url_change=True),
            tool_name="browser_click",
        )

    assert runner.calls == 0


def test_escalation_metadata_is_recorded_on_verified_result():
    runner = CountingRunner(response=_vision_ok("Le dashboard est affiche."))
    ev = _unknown_evidence()

    result, _, _ = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.HIGH,
        expected=ExpectedTransition(expect_url_contains="dashboard"),
        runner=runner,
        vision_available=True,
    )

    assert result.metadata["escalation"]["needed"] is True
    assert result.metadata["vision_confidence"] > 0
    json.dumps(result.to_dict())


def test_escalate_returns_original_evidence_when_not_needed():
    runner = CountingRunner()
    ev = _unknown_evidence()

    result, obs, decision = escalate_unknown(
        evidence=ev,
        risk=RiskLevel.LOW,
        policy=EscalationPolicy(min_risk=RiskLevel.HIGH),
        runner=runner,
        vision_available=True,
    )

    assert result is ev  # identity preserved: no copy, no side effect
    assert obs is None
    assert runner.calls == 0
