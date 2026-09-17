"""H2.0-022 Phase B — RED tests for the qualified-appearance contract.

CONTRACT FROZEN BY ARBITRATION (H2.0-021):

  · `expect_appearing` NAMES the expected element category. It counts as a
    claim in `has_any_claim()` — otherwise "X must appear" would paradoxically
    be treated as "no expectation at all".
  · The category vocabulary is CLOSED to four values:
        dialog · overlay · error · blocking
  · `obstacle` stays backward compatible as the FIRST obstacle;
    `obstacles` is the complete representation.
  · An expected category is exempted ONLY if it is actually observed.
  · Any other category remains a violation while `expect_no_obstacles=True`.
  · An expected category that is ABSENT is never turned into success → UNKNOWN.
  · With `expect_appearing=None`, existing behaviour is UNCHANGED.

NOTHING IS TO BE FIXED AFTER RED. These tests are expected to fail today.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.perception import vision_escalation as ve  # noqa: E402
from agent.verification.evidence import ExpectedTransition, Outcome  # noqa: E402

CATEGORIES = ("dialog", "overlay", "error", "blocking")


def obs(obstacles=(), *, obstacle=None, confidence=0.9, text="A banner appeared."):
    """Build a VisionObservation carrying the full obstacle representation.

    `obstacle` defaults to the first element of `obstacles`, which is the
    documented backward-compatible rule.
    """
    first = obstacle if obstacle is not None else (obstacles[0] if obstacles else None)
    return ve.VisionObservation(
        observation=text,
        obstacle=first,
        obstacles=tuple(obstacles),
        confidence=confidence,
        source="auxiliary",
    )


def judge(observation, expected):
    return ve.judge_observation(observation=observation, expected=expected)


# ── 1. expected appearance alone → VERIFIED ──────────────────────────────
def test_expected_appearance_alone_is_satisfaction():
    expected = ExpectedTransition(expect_appearing="overlay")
    outcome, reasons = judge(obs(("banner",)), expected)
    assert outcome is Outcome.VERIFIED, (
        f"an observed expected element must satisfy the claim, got {outcome}: {reasons}"
    )


# ── 2. expected appearance + unexpected captcha → FAILED ─────────────────
def test_expected_appearance_plus_unexpected_captcha_is_violation():
    expected = ExpectedTransition(expect_appearing="overlay")
    outcome, reasons = judge(obs(("banner", "captcha")), expected)
    assert outcome is Outcome.FAILED, (
        "the expected overlay is exempted, but the captcha is not — the intent "
        f"must stay detectable, got {outcome}: {reasons}"
    )


# ── 3. expected appearance + unexpected error → FAILED ───────────────────
def test_expected_appearance_plus_unexpected_error_is_violation():
    expected = ExpectedTransition(expect_appearing="overlay")
    outcome, reasons = judge(obs(("banner", "error")), expected)
    assert outcome is Outcome.FAILED, f"got {outcome}: {reasons}"


# ── 4. expected element absent → UNKNOWN (never a manufactured success) ──
def test_expected_element_absent_is_unknown():
    expected = ExpectedTransition(expect_appearing="overlay")
    outcome, reasons = judge(obs(()), expected)
    assert outcome is Outcome.UNKNOWN, (
        "an expectation whose element never appeared must not be upgraded to a "
        f"success, got {outcome}: {reasons}"
    )


# ── 5. no expected appearance + obstacle → FAILED (non-regression) ───────
def test_no_expected_appearance_with_obstacle_is_violation():
    expected = ExpectedTransition(expect_dom_change=True)
    outcome, reasons = judge(obs(("banner",)), expected)
    assert outcome is Outcome.FAILED, (
        "with no declared appearance the historical behaviour must hold, "
        f"got {outcome}: {reasons}"
    )


# ── 6. no expected appearance, no obstacle → historical behaviour ────────
def test_no_expected_appearance_no_obstacle_is_unchanged():
    expected = ExpectedTransition(expect_dom_change=True)
    outcome, _reasons = judge(obs(()), expected)
    # No satisfactions and no violations: the judge stays silent.
    assert outcome is Outcome.UNKNOWN


# ── 7. expect_no_obstacles still defaults to True ────────────────────────
def test_expect_no_obstacles_default_is_still_true():
    assert ExpectedTransition().expect_no_obstacles is True, (
        "the invariant from H2.0-021: expect_no_obstacles must never be weakened"
    )
    assert ExpectedTransition(expect_appearing="overlay").expect_no_obstacles is True


# ── 8. obstacle == obstacles[0] (backward compatibility) ─────────────────
def test_obstacle_is_the_first_of_obstacles():
    observation = obs(("banner", "captcha"))
    assert observation.obstacles == ("banner", "captcha")
    assert observation.obstacle == "banner", (
        "the scalar must remain the first obstacle so existing consumers are unaffected"
    )


# ── 9. the four categories are classified ────────────────────────────────
@pytest.mark.parametrize(
    ("keyword", "category"),
    [
        ("modal", "dialog"),
        ("modale", "dialog"),
        ("popup", "dialog"),
        ("banner", "overlay"),
        ("bandeau", "overlay"),
        ("overlay", "overlay"),
        ("error", "error"),
        ("erreur", "error"),
        ("captcha", "blocking"),
        ("recaptcha", "blocking"),
    ],
)
def test_keyword_is_classified_into_a_closed_category(keyword, category):
    assert ve.obstacle_category(keyword) == category
    assert category in CATEGORIES


def test_unknown_keyword_has_no_category():
    assert ve.obstacle_category("flibbertigibbet") is None, (
        "the vocabulary is closed: an unknown keyword must not invent a category"
    )


# ── 10. extraction collects ALL obstacles, not just the first ────────────
def test_extraction_collects_every_obstacle():
    text = "A banner is displayed. A captcha is also blocking the page."
    found = ve._extract_obstacles(text)
    assert "banner" in found and "captcha" in found, (
        f"both obstacles must be represented, got {found}"
    )


# ── 11. has_any_claim() is True with ONLY expect_appearing ───────────────
def test_has_any_claim_with_only_expect_appearing():
    expected = ExpectedTransition(expect_appearing="overlay")
    assert expected.has_any_claim() is True, (
        "an expectation that declares an appearing element IS a claim — "
        "otherwise 'X must appear' would count as 'no expectation'"
    )


# ── 12. an unknown category never exempts anything ───────────────────────
def test_unknown_expected_category_does_not_exempt():
    expected = ExpectedTransition(expect_appearing="flibbertigibbet")
    outcome, _reasons = judge(obs(("banner",)), expected)
    assert outcome is Outcome.FAILED, (
        "only one of the four defined categories may be exempted; an undefined "
        "category must not silently authorise an obstacle"
    )


# ── 13. END-TO-END: the real pipeline honours the exemption ──────────────
#     _parse_observation attaches its own "obstacle detected: …" note. The
#     exemption must survive it, otherwise the production path would never
#     reach a satisfaction.
def _real(text):
    return ve._parse_observation(text, source="auxiliary", screenshot_path=None)


def test_production_path_expected_appearance_is_verified():
    observation = _real("A banner is displayed on the page.")
    assert observation.obstacles == ("banner",)
    assert any("obstacle detected" in c for c in observation.contradictions), (
        "precondition: the extractor does attach its own note"
    )
    outcome, reasons = judge(
        observation, ExpectedTransition(expect_appearing="overlay", expect_dom_change=True)
    )
    assert outcome is Outcome.VERIFIED, (
        "the extractor's own note must not block the satisfaction, "
        f"got {outcome}: {reasons}"
    )


def test_production_path_unexpected_obstacle_still_fails():
    observation = _real("A banner is displayed. A captcha is blocking the page.")
    outcome, reasons = judge(observation, ExpectedTransition(expect_appearing="overlay"))
    assert outcome is Outcome.FAILED, f"got {outcome}: {reasons}"


def test_production_path_without_appearance_is_unchanged():
    observation = _real("A banner is displayed on the page.")
    outcome, reasons = judge(observation, ExpectedTransition(expect_dom_change=True))
    assert outcome is Outcome.FAILED, (
        f"without a declared appearance the historical verdict must hold, got {outcome}: {reasons}"
    )

