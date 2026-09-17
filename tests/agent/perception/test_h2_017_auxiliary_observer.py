"""H2.0-017 — the escalation must obtain a SYNCHRONOUS textual analysis.

Context: the native fast path attaches the screenshot to the conversation and
returns a multimodal envelope. That is correct for the conversation, but H2.0
verifies inside the same action and can never see the next turn — so it used to
receive a placeholder and the verifier concluded "vision_inconclusive".

Fix: when the envelope comes back, H2.0 asks an auxiliary LLM synchronously
(DeepSeek, which measured 4.2 s vs Gemini's 9.3 s on the same screenshot).

These tests must FAIL against the current implementation.
No network: the LLM call is injected through a seam.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent.perception import vision_escalation as ve  # noqa: E402


@pytest.fixture
def shot(tmp_path):
    """A real file: the helper reads the screenshot from disk."""
    p = tmp_path / "shot.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes")
    return str(p)


def _envelope(path: str) -> dict:
    """The shape browser_vision returns on the native fast path."""
    return {
        "_multimodal": True,
        "content": [
            {"type": "text", "text": "Screenshot attached."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        ],
        "text_summary": f"Screenshot path: {path}",
        "meta": {"screenshot_path": path},
    }


def _native_runner(envelope: dict):
    return lambda *, question, annotate, task_id: envelope


ANALYSIS = (
    "## Structure de la page\n"
    "Titre principal (h1) : « Banc non idempotent »\n"
    "Aucun message d'erreur, aucune modale ouverte, aucun bandeau/objet bloquant."
)


def _aux_ok(text: str = ANALYSIS):
    """A chat-completion-shaped object, like call_llm returns."""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = text
    return lambda **kwargs: resp


# ── 1. a native envelope now yields a REAL textual analysis ──────────────
def test_native_envelope_yields_real_analysis(shot):
    obs = ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=_native_runner(_envelope(shot)),
        aux_runner=_aux_ok(),
    )
    assert obs.source == "auxiliary", (
        "the observation must come from the synchronous auxiliary call, "
        "not from the native placeholder"
    )
    assert "Banc non idempotent" in obs.observation
    assert obs.observation != "(screenshot attached natively to the conversation)"


# ── 2. the observation is parseable into the verifier's contract ─────────
def test_analysis_is_parsed_into_the_observation_contract(shot):
    obs = ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=_native_runner(_envelope(shot)),
        aux_runner=_aux_ok(),
    )
    # VisionObservation is what the verifier consumes — the full contract holds.
    assert obs.observation
    assert isinstance(obs.elements, tuple)
    assert obs.error is None
    assert obs.screenshot_path == shot


# ── 3. an auxiliary failure must NOT break anything ──────────────────────
def test_auxiliary_failure_falls_back_cleanly(shot):
    def boom(**kwargs):
        raise RuntimeError("aux provider exploded")

    obs = ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=_native_runner(_envelope(shot)),
        aux_runner=boom,
    )
    # Degrades to the previous, honest behaviour — never raises.
    assert obs.source in {"native", "unavailable"}
    assert obs.observation == "(screenshot attached natively to the conversation)"


# ── 4. an EMPTY response must never become proof ─────────────────────────
def test_empty_auxiliary_response_is_not_proof(shot):
    obs = ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=_native_runner(_envelope(shot)),
        aux_runner=_aux_ok("   "),
    )
    assert obs.observation == "(screenshot attached natively to the conversation)", (
        "a whitespace-only response must not be recorded as an analysis"
    )
    assert "   " != obs.observation


# ── 5. the fallback keeps the screenshot path for debugging ──────────────
def test_fallback_preserves_screenshot_path(shot):
    obs = ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=_native_runner(_envelope(shot)),
        aux_runner=_aux_ok(""),
    )
    assert obs.screenshot_path == shot


# ── 6. a NON-native payload is untouched by the new path ─────────────────
def test_non_native_payload_unchanged():
    """The ordinary auxiliary path must behave exactly as before."""
    plain = {"success": True, "analysis": "Un modal est ouvert.", "screenshot_path": "/tmp/x.png"}
    obs = ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=lambda *, question, annotate, task_id: plain,
        aux_runner=_aux_ok("SHOULD NOT BE CALLED"),
    )
    assert "Un modal est ouvert." in obs.observation
    assert "SHOULD NOT BE CALLED" not in obs.observation


# ── 7. the auxiliary call uses a budget large enough to avoid empty output ─
def test_auxiliary_call_uses_a_safe_token_budget(shot):
    seen: dict = {}
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = ANALYSIS

    def capture(**kwargs):
        seen.update(kwargs)
        return resp

    ve.observe_with_vision(
        question="Describe what is visible.",
        task_id="t",
        runner=_native_runner(_envelope(shot)),
        aux_runner=capture,
    )

    assert seen.get("task") == "vision"
    budget = seen.get("max_tokens")
    assert isinstance(budget, int) and budget >= 600, (
        f"budget {budget!r} is below the measured-safe threshold; DeepSeek is a "
        "reasoning model and burns the budget before emitting content"
    )
    assert seen.get("messages"), "an image message must actually be sent"
