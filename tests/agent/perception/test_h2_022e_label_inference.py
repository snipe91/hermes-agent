"""H2.0-022 Phase E — RED tests for label-inference of the expected category.

CONTRACT FROZEN BY ARBITRATION:

  · Explicit > inference. Priority already guaranteed by
    `begin_observation(expected=…)` (integration.py:229) — the inference is only
    reached when the caller declared nothing.
  · Inference requires an APPEARANCE VERB **and** a CATEGORISABLE OBJECT.
  · Vocabulary closed to dialog / overlay / error / blocking.
  · An ambiguous label yields `expect_appearing=None` — never a guess.
  · Inference touches neither `expect_no_obstacles` nor `expect_dom_change`.
  · A label that yields no category must NEVER authorise an obstacle.

NOTHING IS TO BE FIXED AFTER RED. `intent_from_label()` is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.observation import VerificationMode, begin_observation  # noqa: E402
from agent.observation.ledger import DecisionLedger  # noqa: E402
from agent.perception import vision_escalation as ve  # noqa: E402
from agent.perception.intent import build_intent, intent_from_label  # noqa: E402
from agent.perception.world_state import WorldState  # noqa: E402
from agent.verification.evidence import ExpectedTransition, Outcome  # noqa: E402


def appearing(label: str) -> str | None:
    """The category the label inference produces, or None."""
    expected, _human, _src = intent_from_label(label)
    if expected is None:
        return None
    return getattr(expected, "expect_appearing", None)


def expectation_of(label: str, ref: str = "@e5") -> ExpectedTransition | None:
    """The expectation the production path derives for a click on that label."""
    snap = f'- button "{label}" [ref={ref.lstrip("@")}]'
    inferred = build_intent(
        "browser_click", {"ref": ref}, snapshot_text=snap, risk_level="medium"
    )
    return inferred.expected_transition


def obs(text: str):
    return ve._parse_observation(text, source="auxiliary", screenshot_path=None)


# ══ A. THE INFERENCE RULE ════════════════════════════════════════════════
# ── 1-5. appearance verb + categorisable object → the category ───────────
def test_infers_overlay_from_afficher_le_bandeau():
    assert appearing("Afficher le bandeau") == "overlay"


def test_infers_dialog_from_ouvrir_le_modal():
    assert appearing("Ouvrir le modal") == "dialog"


def test_infers_error_from_afficher_un_message_derreur():
    assert appearing("Afficher un message d'erreur") == "error"


def test_infers_blocking_from_afficher_un_captcha():
    assert appearing("Afficher un captcha") == "blocking"


def test_infers_overlay_from_english_banner():
    """The gap found while evaluating the rules in Phase D."""
    assert appearing("Display the banner") == "overlay"


# ── 6-10. ambiguous label → None, never a guess ──────────────────────────
def test_ambiguous_ajouter_un_element_yields_none():
    assert appearing("Ajouter un élément") is None


def test_bare_verb_afficher_yields_none():
    assert appearing("Afficher") is None


def test_bare_verb_ouvrir_yields_none():
    assert appearing("Ouvrir") is None


def test_verb_with_uncategorisable_object_yields_none():
    assert appearing("Ouvrir le menu") is None


def test_inert_label_yields_none():
    assert appearing("Ne rien faire") is None


# ── 11-12. the inference leaves the other claims untouched ───────────────
def test_inference_preserves_expect_no_obstacles():
    expected, _human, _src = intent_from_label("Afficher le bandeau")
    assert expected is not None
    assert expected.expect_no_obstacles is True, (
        "the inference supplies a category; it must never weaken the obstacle control"
    )


def test_inference_preserves_expect_dom_change():
    expected, _human, _src = intent_from_label("Afficher le bandeau")
    assert expected is not None
    assert expected.expect_dom_change is True, (
        "the historical mutation claim must survive the enrichment"
    )


# ══ B. EXPLICIT > INFERENCE ══════════════════════════════════════════════
# ── 13. a divergent explicit expectation is not overwritten ──────────────
def test_explicit_category_beats_a_divergent_label():
    """The label would infer `overlay`; the caller explicitly says `dialog`."""
    explicit = ExpectedTransition(description="explicit", expect_appearing="dialog")
    inferred = build_intent(
        "browser_click",
        {"ref": "@e5"},
        expected=explicit,
        snapshot_text='- button "Afficher le bandeau" [ref=e5]',
        risk_level="medium",
    )
    assert inferred.expected_transition is explicit, (
        "the explicit expectation must be returned as-is, not rebuilt from the label"
    )
    assert inferred.expected_transition is not None
    assert inferred.expected_transition.expect_appearing == "dialog", (
        "the fallback must not be able to override the caller's declaration"
    )


# ── 14. the same, through the real observation entry point ───────────────
def test_begin_observation_keeps_the_explicit_category(tmp_path):
    class _Observer:
        calls = 0

        def capture(self, **_kwargs):
            type(self).calls += 1
            return WorldState(
                task_id="e5-priority",
                url="file:///bench.html",
                accessibility_snapshot='- button "Afficher le bandeau" [ref=e5]',
                element_count=3,
            )

    explicit = ExpectedTransition(description="explicit", expect_appearing="dialog")
    ctx = begin_observation(
        "browser_click",
        {"ref": "@e5"},
        "e5-priority",
        mode=VerificationMode.OBSERVE,
        observer=_Observer(),
        ledger=DecisionLedger(task_id="e5-priority", directory=tmp_path),
        expected=explicit,
    )

    assert ctx is not None, "observation should have been set up"
    assert ctx.expected is explicit
    assert ctx.expected.expect_appearing == "dialog", (
        "the label says 'Afficher le bandeau' (overlay) but the caller said dialog"
    )


# ══ C. END-TO-END — the inference feeds the Phase C contract ═════════════
# ── 15. declared banner observed → VERIFIED ──────────────────────────────
def test_e2e_expected_banner_is_verified():
    expected = expectation_of("Afficher le bandeau")
    assert expected is not None and expected.expect_appearing == "overlay", (
        "precondition: the label must actually yield the overlay category"
    )
    outcome, reasons = ve.judge_observation(
        observation=obs("A banner is displayed on the page."), expected=expected
    )
    assert outcome is Outcome.VERIFIED, f"got {outcome}: {reasons}"


# ── 16. declared banner + unexpected captcha → FAILED ────────────────────
def test_e2e_expected_banner_with_unexpected_captcha_fails():
    expected = expectation_of("Afficher le bandeau")
    assert expected is not None and expected.expect_appearing == "overlay"
    outcome, reasons = ve.judge_observation(
        observation=obs("A banner is displayed. A captcha is blocking the page."),
        expected=expected,
    )
    assert outcome is Outcome.FAILED, f"got {outcome}: {reasons}"


# ── 17. ambiguous label must NOT authorise an obstacle ───────────────────
def test_e2e_ambiguous_label_does_not_authorise_an_obstacle():
    expected = expectation_of("Ajouter un élément")
    assert expected is not None, "the mutation branch still yields a dom-change claim"
    assert expected.expect_appearing is None, (
        "no category may be fabricated for an ambiguous label"
    )
    outcome, reasons = ve.judge_observation(
        observation=obs("A banner is displayed on the page."), expected=expected
    )
    assert outcome is Outcome.FAILED, (
        "a label we know nothing about must not tolerate any obstacle, "
        f"got {outcome}: {reasons}"
    )
