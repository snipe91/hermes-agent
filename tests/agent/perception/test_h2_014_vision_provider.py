"""H2.0-014 — vision provider resolution: gemini must be selectable.

These tests exercise the EXISTING resolution machinery only. No network call,
no API key, no new transport path is introduced: the provider router already
knows "gemini", so the work is to prove it resolves correctly for task=vision
and that the unavailability latch keeps behaving.

A fake client object stands in for the real one — nothing here reaches Google.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import agent.auxiliary_client as ac  # noqa: E402
import agent.perception.vision_escalation as ve  # noqa: E402


# ── 1. gemini is a recognised vision provider ─────────────────────────────
def test_gemini_is_recognised_as_vision_provider():
    for alias in ("gemini", "google", "google-gemini", "google-ai-studio"):
        assert ac._normalize_vision_provider(alias) == "gemini", (
            f"{alias!r} must normalise to the canonical 'gemini' provider"
        )


# ── 2. gemini has NO static vision default — it must be configured ────────
def test_gemini_has_no_static_vision_default():
    """Established by inspection: _PROVIDER_VISION_MODELS only holds xiaomi/zai.

    gemini therefore cannot rely on an automatic default for task=vision; the
    model must be named explicitly in configuration. This test documents that
    fact so nobody assumes an implicit default exists.
    """
    assert "gemini" not in ac._PROVIDER_VISION_MODELS, (
        "if gemini ever gains a static vision default, revisit the docs and "
        "the auxiliary.vision configuration guidance"
    )
    assert ac._resolve_provider_vision_default("gemini") is None


# ── 3. an explicitly configured gemini model is what reaches the client ──
def test_explicit_gemini_model_is_used():
    """The path that matters: auxiliary.vision.model names the id."""
    seen: dict = {}

    def fake_resolve(task, provider, model, base_url, api_key):
        seen.update(task=task, provider=provider, model=model)
        return provider, model, base_url, api_key, None

    with patch.object(ac, "_resolve_task_provider_model", fake_resolve), \
            patch.object(ac, "_resolve_strict_vision_backend",
                         lambda p, m=None: (MagicMock(), m)):
        ac.resolve_vision_provider_client(
            provider="gemini", model="gemini-3.6-flash"
        )

    assert seen["task"] == "vision"
    assert seen["provider"] == "gemini"
    assert seen["model"] == "gemini-3.6-flash"


# ── 4. gemini without an explicit model is a documented dead end ─────────
def test_gemini_without_explicit_model_yields_no_client():
    """Documents the consequence of the missing static default.

    With no model configured and no static default, the resolver cannot build a
    client. This is why the configuration MUST name the model — and why the
    project must not rely on an implicit gemini default.
    """
    with patch.object(ac, "_resolve_task_provider_model",
                      lambda task, p, m, base_url, api_key:
                      ("gemini", None, base_url, api_key, None)):
        provider, client, model = ac.resolve_vision_provider_client(provider="gemini")

    assert client is None, (
        "no model + no static default must not fabricate a client; the call "
        "fails cleanly instead"
    )


# ── 5. a base_url override wins, without a new transport path ─────────────
def test_base_url_override_is_forwarded():
    """`base_url` is an existing override, not a new route.

    This is what makes a local/other endpoint possible later — but nothing
    here opens a socket.
    """
    seen: dict = {}

    def fake_resolve(task, provider, model, base_url, api_key):
        seen.update(model=model, base_url=base_url, api_key=api_key)
        return provider, model, base_url, api_key, None

    with patch.object(ac, "_resolve_task_provider_model", fake_resolve), \
            patch.object(ac, "_resolve_strict_vision_backend",
                         lambda p, m=None: (MagicMock(), m)):
        ac.resolve_vision_provider_client(
            provider="gemini", model="gemini-flash-latest",
            base_url="https://example.invalid/v1", api_key="dummy",
        )

    assert seen["base_url"] == "https://example.invalid/v1"
    assert seen["model"] == "gemini-flash-latest"


# ── 6. the unavailability latch still short-circuits ─────────────────────
def test_latch_still_reports_unavailable():
    """The latch is intentional (H2.0-006): once proven absent, stop trying.

    It must remain a proven-fact flag, never a live network probe.
    """
    with patch.object(ve, "_VISION_UNAVAILABLE", True):
        assert ve.vision_is_available() is False


# ── 7. availability stays optimistic until proven otherwise ──────────────
def test_availability_is_optimistic_before_proof():
    with patch.object(ve, "_VISION_UNAVAILABLE", False):
        assert ve.vision_is_available() is True, (
            "no proof of absence => optimistically available; the first call "
            "settles the question"
        )


# ── 8. provider-missing errors are still classified as such ──────────────
def test_provider_missing_error_is_recognised():
    """The latch is set by a specific error signature — keep it stable."""
    fn = getattr(ve, "is_provider_missing_error", None)
    assert fn is not None, "is_provider_missing_error must exist for the latch"

    assert fn("No LLM provider configured for task=vision provider=auto") is True
    assert fn("some unrelated timeout while decoding png") is False


# ── 9. a successful analysis propagates through VisionObservation ─────────
def test_successful_analysis_propagates():
    """VisionObservation carries the raw analysis, never a verdict.

    VISION = OBSERVER / VERIFIER = JUDGE: the analysis is text, the confidence
    is derived from hedging language, and the source records where it came from.
    """
    obs = ve.VisionObservation(
        observation="There are 10 buttons visible.",
        source="auxiliary",
        confidence=0.7,
        screenshot_path="/tmp/x.png",
    )
    assert obs.source == "auxiliary"
    assert "10 buttons" in obs.observation
    assert obs.screenshot_path == "/tmp/x.png"
    assert obs.error is None


# ── 10. an unavailable vision observation stays a first-class value ──────
def test_unavailable_observation_is_explicit():
    obs = ve.VisionObservation(source="unavailable", error="no provider")
    assert obs.source == "unavailable"
    assert obs.error == "no provider"
    assert obs.observation == ""
