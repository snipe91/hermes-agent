"""H2.0-019 — obstacle extraction must read negation and context.

The real failure (H2.0-018): DeepSeek wrote

    "No error message, no modal dialog, no overlay/banner, and no blocking
     element is present."

…and _parse_observation saw the word "error" → obstacle='error' → the verifier
raised a violation → FAILED. The analysis said the OPPOSITE of what was
extracted.

These tests pin the distinction the fix must preserve:
    "A modal dialog is currently open."      -> obstacle
    "No modal dialog is open."               -> no obstacle
    "Section C describes a modal component." -> no obstacle
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.perception.vision_escalation import _parse_observation  # noqa: E402


def parse(text: str):
    return _parse_observation(text, source="auxiliary", screenshot_path=None)


# ── NEGATION: the exact phrases that caused the false positives ──────────
def test_no_error_message():
    assert parse("No error message is present.").obstacle is None


def test_no_errors_plural():
    assert parse("There are no errors on this page.").obstacle is None


def test_no_modal_dialog():
    assert parse("No modal dialog is open.").obstacle is None


def test_no_overlay_or_banner():
    assert parse("No overlay or banner is visible.").obstacle is None


def test_no_blocking_element():
    assert parse("There is no blocking element.").obstacle is None


def test_the_real_analysis_from_h2_0_018():
    """Verbatim sentence that produced obstacle='error' in the audit."""
    text = (
        "The page consists of a vertical stack of ten bordered, rounded cards. "
        "No error message, no modal dialog, no overlay/banner, and no blocking "
        "element is present."
    )
    assert parse(text).obstacle is None, (
        "this sentence asserts the ABSENCE of every obstacle; extracting one "
        "inverts its meaning"
    )


def test_negation_with_following_positive():
    """"… no overlay/banner, and no blocking element is present" — chain of negations."""
    assert parse("No captcha, no cookie banner, no error.").obstacle is None


def test_french_negation():
    assert parse("Aucune modale n'est ouverte.").obstacle is None
    assert parse("Pas de message d'erreur.").obstacle is None


# ── DESCRIPTIVE MENTION: a label is not an obstacle ─────────────────────
def test_nominal_section_mention():
    assert parse("Section C — modal").obstacle is None


def test_nominal_mention_inside_a_description():
    text = (
        "Panels visible, top to bottom: "
        "- A — clic simple: button 'Bouton simple'. "
        "- C — modal (toggle + compteur interne). "
        "- D — overlay."
    )
    assert parse(text).obstacle is None, (
        "listing the page's own section labels is not reporting an obstacle"
    )


def test_markdown_label_mention():
    assert parse("**C — modal**").obstacle is None


# ── POSITIVE ASSERTION: must still be detected ──────────────────────────
def test_positive_modal_is_detected():
    obs = parse("A modal dialog is currently open.")
    assert obs.obstacle is not None, "an open modal IS an obstacle"


def test_positive_error_is_detected():
    obs = parse("An error message is displayed.")
    assert obs.obstacle is not None


def test_positive_french():
    obs = parse("Une modale est ouverte et bloque la page.")
    assert obs.obstacle is not None


def test_positive_captcha():
    obs = parse("A reCAPTCHA challenge is blocking the page.")
    assert obs.obstacle is not None


# ── MIXED: affirmation and negation in the same analysis ────────────────
def test_mixed_negation_then_positive():
    obs = parse("No error is shown, but a modal is open.")
    assert obs.obstacle is not None, (
        "a negated obstacle must not mask a real one stated elsewhere"
    )


def test_mixed_positive_then_negation():
    obs = parse("A modal is open. There is no error message.")
    assert obs.obstacle is not None, "the asserted modal remains an obstacle"


def test_mixed_only_negations_stay_clean():
    obs = parse("No modal is open. No error message. No overlay.")
    assert obs.obstacle is None


# ── QUOTED UI LABEL: the name of a control is not a report ──────────────
def test_quoted_button_label_is_not_an_obstacle():
    """The real text from the audit: a button is NAMED 'Afficher le modal'."""
    assert parse('button "Afficher le modal"').obstacle is None


def test_quoted_french_label_is_not_an_obstacle():
    assert parse("bouton « Afficher le modal »").obstacle is None


def test_section_enumeration_clause_is_descriptive():
    """Verbatim shape from the audit: the analysis lists the page's sections."""
    text = '  - **C — modal:** button "Afficher le modal"   - **D — overlay:** button "Afficher un bandeau"'
    assert parse(text).obstacle is None


def test_full_audit_excerpt_yields_no_obstacle():
    """A real excerpt: title + enumeration of sections A..J."""
    text = (
        "Visible on the page:  - **Main heading:** “Banc de test H2.0” - A sequence "
        'of bordered sections labeled **A** through **J**:   - **A — clic simple:** '
        'button “Bouton simple”; status text “en attente”   - **C — modal:** button '
        '“Afficher le modal”   - **D — overlay:** button “Afficher un bandeau”'
    )
    assert parse(text).obstacle is None, (
        "describing the page's own sections must never be read as an obstacle"
    )


def test_quoted_label_does_not_mask_a_real_report():
    """A quoted label AND a genuine report in the same analysis."""
    text = 'button "Afficher le modal" is present. A modal dialog is currently open.'
    obs = parse(text)
    assert obs.obstacle is not None, (
        "the quoted label must be skipped without hiding the real assertion"
    )


# ── MARKDOWN HEADING: a category title is not a report ──────────────────
def test_markdown_heading_is_not_an_obstacle():
    """Verbatim from the audit: DeepSeek's section title."""
    assert parse("## Modals, banners, error messages, blocking elements").obstacle is None


def test_heading_does_not_mask_the_body():
    text = "## Modals, banners, error messages\nNo modal is open. A modal dialog is currently open."
    obs = parse(text)
    assert obs.obstacle is not None, "the heading is skipped; the body still reports"


def test_heading_with_a_real_report_under_it():
    text = "### Error messages\nAn error message is displayed at the top of the form."
    obs = parse(text)
    assert obs.obstacle is not None


# ── the rest of the observation contract is unchanged ───────────────────
def test_contradictions_follow_the_obstacle():
    obs = parse("A modal dialog is currently open.")
    assert any("obstacle detected" in c for c in obs.contradictions)

    clean = parse("No modal dialog is open.")
    assert not any("obstacle detected" in c for c in clean.contradictions)


def test_elements_still_extracted():
    obs = parse("No error message. A button and a heading are visible.")
    assert "button" in obs.elements
    assert "heading" in obs.elements
    assert obs.obstacle is None
